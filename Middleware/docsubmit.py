#!/usr/bin/env python3

# TODO! Add option for submitting a folder containing multiple files.

import argparse
import sys
from datetime import datetime
from pathlib import Path

SUPPORTED_FILETYPES = {".pdf", ".png", ".jpg"} # Are there more?

def main():
    # Read and retrieve the path from command line.
    ap = argparse.ArgumentParser()
    ap.add_argument("path", type=Path)
    args = ap.parse_args()

    # Validate the input
    path = validate_input(args.path)

    # Decide names. We keep the input name but add the .json suffix since we will return JSON.
    out_name = path.name + ".json"

    # Make a fresh folder for this submission, named by timestamp.
    job_dir = create_submission_folder(path)

    # Create final submission file and write its contents.
    create_submission_file(path.name, out_name, path, job_dir)



def validate_input(path: Path) -> Path:
    abs_path = path.resolve() # Turns the path into absolute path
    if not abs_path.is_file():
        sys.exit(f"Not a file: {abs_path}")
    if abs_path.suffix.lower() not in SUPPORTED_FILETYPES:
        sys.exit(f"Unsupported file type: {abs_path.suffix}")
    return abs_path

def create_submission_folder(path: Path):
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    job_dir = Path("docsubmit_jobs").resolve() / stamp
    job_dir.mkdir(parents=True)
    return job_dir

def create_submission_file(path_name: str, out_name: str, path: Path, job_dir: Path):
    # Create submission file and add content
    sub_path = job_dir / "job.sub"
    submit_text = f"""\
executable            = read_doc.sh
arguments             = "{path.name} {out_name}"

should_transfer_files = YES
transfer_input_files  = {path}
transfer_output_files = {out_name}

initialdir            = {job_dir}
output                = job.out
error                 = job.err
log                   = job.log



queue
"""
    sub_path.write_text(submit_text)

    #Tell user location of submit file:
    print(f"Wrote {sub_path}")

    return

if __name__ == "__main__":
    main()