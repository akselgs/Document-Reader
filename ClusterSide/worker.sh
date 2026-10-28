#!/bin/bash
# worker.sh - executable that the HTCondor .sub file points to.
# Usage: ./run_job.sh <input_file>
 
set -euo pipefail   # stop at the first error, treat unset variables as errors
 
INPUT="$1"
CONVERTED="converted_input.dat"
RAW_OUTPUT="raw_output.dat"
RESULT="result.pkl"
CLUSTER_SIDE="$HOME/DocReader/ClusterSide"
 
# 4. Clean up: remove intermediate files. The trap makes this run on success
# and on failure, so scratch files never pile up. The final result is kept.
cleanup() {
    echo "Cleaning up intermediate files"
    rm -f "$CONVERTED" "$RAW_OUTPUT"
}
trap cleanup EXIT

# 1. Check the file format and convert if needed.
# convert.py should copy the file unchanged if it is already in the right format.
echo "Checking/converting input: $INPUT"
python3 "$CLUSTER_SIDE/convert.py" "$INPUT" "$CONVERTED"
 
# 2. Submit the file to the other program (placeholder)
echo "Running model inferencce program"
python3 "$CLUSTER_SIDE/inference.py" "$CONVERTED" "$RAW_OUTPUT"
 
# 3. Serialize the data
#echo "Serializing output"
#python3 serialize.py "$RAW_OUTPUT" "$RESULT"

#echo "Done: $RESULT"
echo "Done: $RAW_OUTPUT"