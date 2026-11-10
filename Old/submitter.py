#Transfers documents and job files to the cluster via SSH and submits the jobs to HTCondor

#!/usr/bin/env python3
"""Copy a folder of HTCondor jobs to a cluster over SSH and submit them.

Usage:
    python submit_jobs.py ./my_jobs user@cluster.example.org
    python submit_jobs.py ./my_jobs user@cluster.example.org --remote-dir /home/user/condor_runs

Assumptions:
  - Each job is described by a *.sub file in the folder.
  - Any input files the jobs need live in the same folder.
  - SSH access works without an interactive password prompt (use ssh keys).
  - ssh, scp and condor_submit are available (locally: ssh/scp, remotely: condor_submit).
"""
import argparse
import subprocess
import sys
from pathlib import Path

import secrets


def run(cmd):
    """Run a command, print its output, and stop the script if it fails."""
    print("$", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.stdout:
        print(result.stdout.strip())
    if result.returncode != 0:
        print(result.stderr.strip(), file=sys.stderr)
        sys.exit(f"Command failed with exit code {result.returncode}")


def main():
    parser = argparse.ArgumentParser(description="Submit HTCondor jobs over SSH")
    parser.add_argument("folder", help="Folder containing the .sub job files")
    parser.add_argument("host", help="SSH target, e.g. user@cluster.example.org")
    parser.add_argument("--remote-dir", default="condor_jobs",
                        help="Directory on the cluster to copy the folder into "
                             "(default: ~/condor_jobs)")
    args = parser.parse_args()

    folder = Path(args.folder).resolve()
    if not folder.is_dir():
        sys.exit(f"Not a folder: {folder}")

    sub_files = sorted(folder.glob("*.sub"))
    if not sub_files:
        sys.exit(f"No .sub files found in {folder}")

    remote_path = f"{args.remote_dir}/{folder.name}"

    # 1. Create the remote directory
    run(["ssh", args.host, f"mkdir -p '{remote_path}'"])

    # 2. Copy the whole folder content (job files + inputs) to the cluster
    run(["scp", "-r", *[str(p) for p in folder.iterdir()], f"{args.host}:{remote_path}/"])

    # 3. Submit each job from within the remote folder
    for sub in sub_files:
        run(["ssh", args.host, f"cd '{remote_path}' && condor_submit '{sub.name}'"])

    print(f"\nSubmitted {len(sub_files)} job description(s) to {args.host}:{remote_path}")


if __name__ == "__main__":
    main()