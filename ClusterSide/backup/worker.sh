#!/bin/bash
# worker.sh - executable that the HTCondor .sub file points to.
# Usage: ./worker.sh <input_file>
# Produces <stem>.txt (full text) and <stem>.json (serialized) in the working directory.

set -euo pipefail
shopt -s nullglob

INPUT="${1:?usage: worker.sh <input_file>}"
STEM="${INPUT%.*}"          # file name without its suffix, same as Python's Path.stem
CLUSTER_SIDE="/share/home/student14/DocReader/ClusterSide"

# 1. Check the file format and convert to PNG pages (pages/page_001.png, ...)
echo "Checking/converting input: $INPUT"
mkdir -p pages raw
python3 "$CLUSTER_SIDE/convert.py" "$INPUT" pages

pages=(pages/page_*.png)
if [ ${#pages[@]} -eq 0 ]; then
    echo "No pages were produced from $INPUT" >&2
    exit 1
fi

# 2. Run the model on each page
for page in "${pages[@]}"; do
    name=$(basename "$page" .png)
    echo "Running model on $name"
    python3 "$CLUSTER_SIDE/inference.py" "$page" "raw/${name}.txt"
done

# 3. Concatenate all page outputs into the full text (page order = file name order)
echo "Concatenating output"
python3 "$CLUSTER_SIDE/concatenate.py" raw/*.txt "$STEM.txt"

# 4. Serialize the full text into JSON
echo "Serializing output"
python3 "$CLUSTER_SIDE/serialize.py" "$STEM.txt" "$STEM.json"

echo "Done: $STEM.txt, $STEM.json"