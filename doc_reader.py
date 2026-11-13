#Main function for running the program. Should handle everything.
# Usage: python doc_reader.py [folder] [host]
# folder: A relative path to the folder containing the patient-reports you want as structured (JSON) output - formated for populating new databases.
# --- Defaults to Test1Docs in the Tests folder.
# host: The host that you connect to. including both username and server adress.
# --- Defaults to my student account and the school's datalab which requires authentification

import argparse
import secrets
import shlex
import subprocess
import sys
from pathlib import Path
from collections import defaultdict
import json
import tempfile
from datetime import datetime, timezone


# Defaults used when the program is run without arguments (for testing)
DEFAULT_FOLDER = Path("Tests\\Test1Docs")               # Relative path to a single test_document when running from project root.
DEFAULT_HOST = "student14@condormaster.datalab"         # ssh host 


REMOTE_BASE = "DocReader/Submissions"   # relative to the remote home
EXECUTABLE = "$ENV(HOME)/DocReader/ClusterSide/worker.sh"

SUB_TEMPLATE = """\
universe                = vanilla
executable              = {executable}
arguments               = {arguments}

should_transfer_files   = IF_NEEDED
transfer_input_files    = {name}
when_to_transfer_output = ON_EXIT
transfer_output_files   = {stem}.txt, {stem}.json

output                  = job.out
error                   = job.err
log                     = job.log

request_cpus            = 1
request_memory          = 600MB
request_disk            = 1GB

max_retries             = 0
notification            = Never

queue
"""

# Valid filetypes within the submission folder
DOCUMENT_SUFFIXES = {".pdf", ".png"}


# Parse arguments - Defaults if not present
def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Generate HTCondor jobs for a folder of documents and submit them."
    )
    parser.add_argument(
        "folder", nargs="?", type=Path, default=DEFAULT_FOLDER,
        help=f"Relative path to folder with documents to process (default: {DEFAULT_FOLDER})",
    )
    parser.add_argument(
        "--host", default=DEFAULT_HOST,
        help=f"SSH host or alias (default: {DEFAULT_HOST})",
    )
    return parser.parse_args(argv)

# Searches for supported filetypes in the submission folder
def find_documents(folder: Path) -> list[Path]:
    """Return the PDF and PNG files directly inside `folder`, sorted by name.
    Raises ValueError if two files would produce the same output names."""
    documents = sorted(
        p for p in folder.iterdir()
        if p.is_file()
        and p.suffix.lower() in DOCUMENT_SUFFIXES
        and not p.name.startswith(".")
    )

    by_stem = defaultdict(list)
    for p in documents:
        by_stem[p.stem.lower()].append(p.name)   # lowercase: Scan.pdf vs scan.png also clash
    clashes = [names for names in by_stem.values() if len(names) > 1]
    if clashes:
        lines = "\n".join("  " + ", ".join(names) for names in clashes)
        raise ValueError(
            "These files would write to the same result files "
            f"(same name apart from the suffix):\n{lines}"
        )
    return documents


class JobError(Exception):
    def __init__(self, message, returncode=None):
        super().__init__(message)
        self.returncode = returncode

def run(cmd):
    result = subprocess.run(cmd, text=True, capture_output=True)
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise JobError(f"{cmd[0]} failed: {detail}", result.returncode)
    return result.stdout

def ssh(args, command):
    return run(["ssh", args.host, command])

def scp(args, sources, destination):
    return run(["scp", *map(str, sources), f"{args.host}:{destination}"])

def condor_arguments(name):
    """HTCondor 'new syntax': whole list in double quotes, each item in single quotes."""
    escaped = name.replace("'", "''").replace('"', '""')
    return f"\"'{escaped}'\""

def ensure_private_base(args):
    """Create the Submissions folder if missing (safe to repeat) and check it is private."""
    base = REMOTE_BASE
    ssh(args, f"umask 077 && mkdir -p {base}")
    mode = ssh(args, f"stat -c %a {base}").strip()
    if mode != "700":
        raise JobError(
            f"Remote folder {base} has mode {mode}, expected 700. "
            f"Fix it with: chmod 700 {base}"
        )

def submit_document(doc: Path, folder: Path, args, run_id: str) -> str:
    """Create a private remote folder for one document, send it, submit it, write the ticket."""
    name, stem = doc.name, doc.stem
    if "," in name or '"' in name:
        raise JobError("file name contains a comma or double quote, which HTCondor can't transfer")

    token = secrets.token_hex(8)
    remote_dir = f"{REMOTE_BASE.rstrip('/')}/{token}"
    q = shlex.quote(remote_dir)

    # Stage 1: nothing is queued yet, so on failure the remote folder is removed.
    try:
        ssh(args, f"umask 077 && mkdir -m 700 {q}")
        created = True
        mode = ssh(args, f"stat -c %a {q}").strip()
        if mode != "700":
            raise JobError(f"remote folder has mode {mode}, expected 700")
        with tempfile.TemporaryDirectory() as tmp:
            sub = Path(tmp) / "job.sub"
            sub.write_text(SUB_TEMPLATE.format(
                executable=EXECUTABLE, arguments=condor_arguments(name), name=name, stem=stem,
            ))
            scp(args, [doc, sub], f"{remote_dir}/")
    except JobError:
        if locals().get("created"):
            subprocess.run(["ssh", args.host, f"rm -rf {q}"]) 
        raise

    # Stage 2: from here the job may be queued, so the folder is only removed
    # when condor_submit clearly failed (ssh itself exits with 255 on connection errors).
    try:
        ssh(args, f"cd {q} && condor_submit job.sub")
    except JobError as e:
        if e.returncode != 255:
            subprocess.run(["ssh", args.host, f"rm -rf {q}"]) 
            raise
        raise JobError(f"connection lost during submit; job may be queued, folder kept: {remote_dir}")

    # Stage 3: ticket. Never delete anything here, the job is running.
    ticket = {
        "token": token,
        "run_id": run_id,
        "host": args.host,
        "remote_dir": remote_dir,
        "document": name,
        "expected_files": [f"{stem}.txt", f"{stem}.json"],
        "submitted": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    try:
        tickets = folder / "tickets"
        tickets.mkdir(exist_ok=True)
        (tickets / f"{name}.ticket.json").write_text(json.dumps(ticket, indent=2))
    except OSError as e:
        raise JobError(f"submitted, but could not write ticket ({e}); remote folder: {remote_dir}")
    return token


def generate_jobs(folder: Path, documents: list[Path], args, run_id: str):
    """Submit every document independently. Returns (succeeded, failed)."""
    ensure_private_base(args)
    succeeded, failed = [], []
    for doc in documents:
        try:
            token = submit_document(doc, folder, args, run_id)
            print(f"  submitted  {doc.name}  ->  {token}")
            succeeded.append(doc)
        except JobError as e:
            print(f"  FAILED     {doc.name}: {e}")
            failed.append(doc)
    return succeeded, failed


def main(argv=None):
    # Parse arguments
    args = parse_args(argv)
    folder = args.folder.expanduser()

    if not folder.is_dir():
        sys.exit(f"Folder not found: {folder}")

    print(f"Folder:      {folder}")
    print(f"Host:        {args.host}")


    # Finding documents in submission folder
    try:
        documents = find_documents(folder)
    except ValueError as e:
        sys.exit(str(e))

    if not documents:
      sys.exit(f"No PDF or PNG files found in {folder}")

    # Create job description files and submit along with documents
    run_id = secrets.token_hex(4)
    try:
        succeeded, failed = generate_jobs(folder, documents, args, run_id)
    except JobError as e:
        sys.exit(f"Error: {e}")

    print(f"Done: {len(succeeded)} submitted, {len(failed)} failed")
    if failed:
        sys.exit(1)



    return True

if __name__ == "__main__":
    main()
