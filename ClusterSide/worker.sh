#!/bin/bash
# worker.sh - executable that the HTCondor .sub file points to.
# Usage: ./worker.sh <input_file>

set -euo pipefail   # stop at the first error, treat unset variables as errors

INPUT="$1"
RESULT="result.txt"
CLUSTER_SIDE="/share/home/student14/DocReader/ClusterSide"

# Clean up: remove intermediate files. The trap makes this run on success
# and on failure, so scratch files never pile up. The final result is kept.
cleanup() {
    echo "Cleaning up intermediate files"
    rm -rf pages
    rm -f raw_page_*.txt
}
# trap cleanup EXIT

# echo "=== Resources on $(hostname) ==="
# free -m || true
# nproc || true
# df -h . || true
# cat /sys/fs/cgroup/memory.max 2>/dev/null || echo "no cgroup v2 memory.max"
# grep -E '^(Memory|RequestMemory|Cpus|Disk) ' "$_CONDOR_MACHINE_AD" "$_CONDOR_JOB_AD" 2>/dev/null || true
# echo "=== input sizes ==="
# ls -lh "$INPUT" || true
# du -sh "${CLUSTER_SIDE:-.}" 2>/dev/null || true

# 1. Check the file format and convert to PNG pages (pages/page_001.png, ...)
echo "Checking/converting input: $INPUT"
mkdir -p pages
python3 "$CLUSTER_SIDE/convert.py" "$INPUT" pages

# 2. Run the model on each page
for page in pages/page_*.png; do
    name=$(basename "$page" .png)
    echo "Running model on $name"
    python3 "$CLUSTER_SIDE/inference.py" "$page" "raw_${name}.txt"
done

# 3. Serialize all page outputs into one result (page order = file name order)
echo "Serializing output"
python3 "$CLUSTER_SIDE/serialize.py" raw_page_*.txt "$RESULT"

echo "Done: $RESULT"