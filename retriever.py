# Ticket retriever for doc_reader.py.
# Usage: python fetch_results.py [folder] [--host HOST]
# folder: the same folder you gave doc_reader.py (it contains the tickets/ subfolder).
# host:   the same host as when submitting.
#
# For every ticket in <folder>/tickets it tries to download <stem>.txt and <stem>.json
# into <folder>/results/ (saved as <document name>.txt / .json) and always tries to keep
# the job's stdout as <document name>.out. If the results are missing it explains why
# (error text, remote folder listing, job output). Afterwards it offers to delete the
# remote folders and tickets of everything that was retrieved.

import json
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path, PurePosixPath
from datetime import datetime

from doc_reader import parse_args, ssh, JobError


def checked_remote_dir(ticket: dict) -> str:
    """Refuse to touch anything that doesn't look like a folder we created."""
    remote_dir, token = ticket["remote_dir"], ticket["token"]
    parts = PurePosixPath(remote_dir).parts
    if (not re.fullmatch(r"[0-9a-f]{16}", token)
            or len(parts) < 2
            or parts[-1] != token
            or remote_dir.startswith("/")
            or ".." in parts):
        raise JobError(f"ticket has an unexpected remote path: {remote_dir!r}")
    return remote_dir


def ssh_cat(args, remote_path: str, local_path: Path):
    """Stream one remote file to disk. Raises JobError if it can't be read."""
    with open(local_path, "wb") as f:
        result = subprocess.run(
            ["ssh", args.host, f"cat {shlex.quote(remote_path)}"],
            stdout=f, stderr=subprocess.PIPE,
        )
    if result.returncode != 0:
        raise JobError(result.stderr.decode(errors="replace").strip() or "file not found",
                       result.returncode)


def print_job_output(out_path: Path):
    out = out_path.read_text(encoding="utf-8", errors="replace")
    print(textwrap.indent(out.rstrip() or "(empty)", "    | "))


def fetch_one(ticket: dict, results: Path, args) -> bool:
    """Download <stem>.txt and <stem>.json. Always tries to keep job.out as well.
    Returns True only if both result files arrived."""
    remote_dir = checked_remote_dir(ticket)
    name = ticket["document"]
    results.mkdir(exist_ok=True)

    # job.out is kept whether or not the results are ready (best effort)
    out_path = results / f"{name}.out"
    try:
        ssh_cat(args, f"{remote_dir}/job.out", out_path)
        have_out = True
    except JobError:
        out_path.unlink(missing_ok=True)      # ssh_cat leaves an empty file behind on failure
        have_out = False

    with tempfile.TemporaryDirectory() as tmp:    # download aside, move in only on success
        downloaded = []
        try:
            for expected in ticket["expected_files"]:
                target = Path(tmp) / expected
                ssh_cat(args, f"{remote_dir}/{expected}", target)
                downloaded.append((target, Path(expected).suffix))
        except JobError as e:
            print(f"  Could not retrieve results for {name}: {e}")
            try:
                listing = ssh(args, f"ls -1 {shlex.quote(remote_dir)}").splitlines()
                print("  Files in the remote folder: " + ", ".join(listing))
                print(f"  Expected: {', '.join(ticket['expected_files'])}")
            except JobError:
                print(f"  Could not list the remote folder. Please check the cluster manually: {remote_dir}")
            if have_out:
                print(f"  Job output so far (saved to {out_path}):")
                print_job_output(out_path)
            return False

        for target, suffix in downloaded:
            shutil.move(str(target), results / f"{name}{suffix}")
    print(f"  retrieved {name}" + (" (with job output)" if have_out else ""))
    return True

def archive_results(folder: Path, results: Path) -> Path | None:
    """Move <folder>/results to <root>/TestResults/<datetime>/<folder name>.

    Layout: <root>/Tests/Test1/results -> <root>/TestResults/<stamp>/Test1
    """
    if not results.is_dir():
        return None
    folder = folder.resolve()
    root = folder.parent.parent                       # the folder that holds Tests/
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")   # no colons: invalid on Windows
    dest = root / "TestResults" / stamp / folder.name
    if dest.exists():
        raise JobError(f"archive folder already exists: {dest}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(results), str(dest))
    return dest

def fetch_main(argv=None):
    sys.stdout.reconfigure(errors="replace")      # job output may contain characters the console can't show
    args = parse_args(argv)
    folder = args.folder.expanduser()
    ticket_files = sorted((folder / "tickets").glob("*.ticket.json"))
    if not ticket_files:
        sys.exit(f"No tickets found in {folder / 'tickets'}")

    results = folder / "results"
    retrieved = []                                # (ticket file, ticket)
    for tf in ticket_files:
        print(tf.name)
        try:
            ticket = json.loads(tf.read_text())
            if fetch_one(ticket, results, args):
                retrieved.append((tf, ticket))
        except (JobError, ValueError, KeyError) as e:
            print(f"  ERROR: {e}")

    pending = len(ticket_files) - len(retrieved)
    print(f"\n{len(retrieved)} retrieved, {pending} not retrieved (tickets kept)")

    if retrieved and input(
        f"Delete {len(retrieved)} remote folder(s) on the cluster and their tickets? [y/N] "
    ).strip().lower() == "y":
        for tf, ticket in retrieved:
            try:
                ssh(args, f"rm -rf {shlex.quote(checked_remote_dir(ticket))}")
                tf.unlink()
                print(f"  cleaned up {ticket['document']}")
            except (JobError, OSError) as e:
                print(f"  cleanup FAILED for {ticket['document']}: {e} (ticket kept)")

    if pending:
        sys.exit(1)
    try:
        dest = archive_results(folder, results)
        if dest:
            print(f"\nMoved results to {dest}")
    except (JobError, OSError) as e:
        print(f"\nCould not archive results: {e} (left in {results})")


if __name__ == "__main__":
    fetch_main()