#Entry point. Accepts the folder path as a terminal argument and orchestrates submissions

import argparse
import sys
import subprocess
import shutil
from datetime import datetime
from pathlib import Path

SUPPORTED_FILETYPES = {".pdf", ".png"}

def main():
    # Parse arguments:
    ### PATH, Host, and name of directory at the Host.
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", 
                    default = ".",
                    type=Path, 
                    help="Folder containing documents")
    ap.add_argument("--host", 
                    default="student14@condormaster.datalab", 
                    help="SSH target, e.g. user@cluster.example.org")
    ap.add_argument("--remote-dir", 
                    default="docksubmits",
                    help="Directory on the cluster to copy the folder into " "(default: ~/condor_jobs)")
    args = ap.parse_args()

    # Extract paths from the folder
    paths = extract_paths(args.path)

    # Main loop for creating job files and submitting documents.
    ### (0). Create the remote directory at the host
    ###
    ### 1. Creates a docsubmits folder and creates a dated folder within
    ###
    ### 2a. Copy the Document into this folder
    ### 2b. Create the job file in this folder
    ### 
    ### 3a. Copy over the folder
    ### 3b. Call condor submit on the submit file
    # 0
    remote_path = f"{args.remote_dir}"
    print("Making remote directory")
    run(["ssh", args.host, f"mkdir -p '{remote_path}'"])
    for p in paths:
        # 1.
        job_dir = create_submission_folder(p)

        # 2a.
        print("Copying file into submission folder")
        shutil.copy(p, job_dir)

        # 2b.
        print("Making job file")
        create_job_file(p, job_dir, remote_path) 

        # 3a.
        print("Transferring submission folder")
        run(["scp", "-r", str(job_dir), f"{args.host}:{remote_path}/"])

        # 3b.
        print("Submitting job")
        sub = job_dir.glob("*.sub")
        for s in sub:
            run(["ssh", args.host, f"cd '{remote_path}/{job_dir.stem}' && condor_submit '{s.name}'"])

    


#Extract absolute paths of the documents in the submitted folder
def extract_paths(path: Path) -> Path:
    abs_path = path.resolve() # Turns the path into absolute path
    if abs_path.is_dir():

        filepaths = [p for p in abs_path.iterdir() if p.suffix.lower() in SUPPORTED_FILETYPES]
        return filepaths
    # if abs_path.suffix.lower() not in SUPPORTED_FILETYPES:
    else:
        (sys.exit(f"Unsupported file type: {abs_path.suffix}"))

    return abs_path

# Creates the .sub file and places it in the submission folder
def create_job_file(path: str, job_dir: str, remote_path: str):
    #TODO this is not finished... Path for input file is wrong maybe?
    doc_path = f"~/{remote_path}/{job_dir.stem}/{path.name}" 
    out_path = f"~/{remote_path}/{job_dir.stem}/"

    sub_path = job_dir / (path.stem.lower() + ".sub")
    submit_text = f"""\
    executable            = $ENV(HOME)/DocReader/ClusterSide/worker.sh
    
    should_transfer_files = NO
    
    arguments             = "{path.name}"
    output                = job.out
    error                 = job.err
    log                   = job.log
    
    queue
    """
    sub_path.write_text(submit_text)
    print(f"Wrote {sub_path}")
    return True

#Create a submission folder with the current datetime within the folder "docsubmit_jobs"
def create_submission_folder(path: Path):
    pathname = path.stem.lower()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-")
    job_dir = Path("docsubmits").resolve() / (stamp + pathname) #TODO: Creates the "outer" docsubmits multiple times which is redundant.
    job_dir.mkdir(parents=True)
    return job_dir

#Submits the submission file and corresponding document to cluster
def submit():
    return True

def run(cmd):
    """Run a command, print its output, and stop the script if it fails."""
    print("$", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.stdout:
        print(result.stdout.strip())
    if result.returncode != 0:
        print(result.stderr.strip(), file=sys.stderr)
        sys.exit(f"Command failed with exit code {result.returncode}")


if __name__ == "__main__":
    main()