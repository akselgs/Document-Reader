#!/bin/bash
# worker.sh - executable that the HTCondor .sub file points to.
# Usage: ./worker.sh <input_file>

set -euo pipefail
shopt -s nullglob

INPUT="${1:?usage: worker.sh <input_file>}"
STEM="${INPUT%.*}"
CLUSTER_SIDE="/share/home/student14/DocReader/ClusterSide"

JOB_START=$(date +%s.%N)
HAVE_TIME=0; [ -x /usr/bin/time ] && HAVE_TIME=1
HAVE_GPU=0;  command -v nvidia-smi >/dev/null 2>&1 && HAVE_GPU=1

# ---------- profiling helpers ----------
disk_report() {
    echo "[DISK] $1"
    echo "  job dir used:     $(du -sh . 2>/dev/null | cut -f1)"
    echo "  job dir free:"
    df -h . | sed 's/^/    /'
    echo "  shared fs free:"
    df -h "$CLUSTER_SIDE" | sed 's/^/    /'
}

# step <label> <command...>  : times the command, reports peak RAM (+ GPU mem)
step() {
    local label="$1"; shift
    local tmp gpulog gpupid=""
    tmp=$(mktemp); gpulog=$(mktemp)
    if [ "$HAVE_GPU" = 1 ]; then
        nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits -lms 500 > "$gpulog" 2>/dev/null &
        gpupid=$!
    fi
    local t0 t1 rc=0
    t0=$(date +%s.%N)
    if [ "$HAVE_TIME" = 1 ]; then
        /usr/bin/time -v -o "$tmp" "$@" || rc=$?
    else
        "$@" || rc=$?
    fi
    t1=$(date +%s.%N)
    [ -n "$gpupid" ] && { kill "$gpupid" 2>/dev/null || true; wait "$gpupid" 2>/dev/null || true; }

    echo "[PROFILE] $label"
    echo "  wall time:        $(echo "$t1 - $t0" | bc) s"
    if [ "$HAVE_TIME" = 1 ]; then
        echo "  peak RAM (RSS):   $(awk -F': ' '/Maximum resident set size/{printf "%.1f MB", $2/1024}' "$tmp")"
        echo "  user/sys CPU:     $(awk -F': ' '/User time/{u=$2} /System time/{s=$2} END{print u" s / "s" s"}' "$tmp")"
    fi
    if [ "$HAVE_GPU" = 1 ] && [ -s "$gpulog" ]; then
        echo "  peak GPU mem:     $(sort -n "$gpulog" | tail -1) MiB"
    fi
    echo "  exit code:        $rc"
    rm -f "$tmp" "$gpulog"
    return "$rc"
}

# ---------- environment snapshot ----------
echo "===== ENVIRONMENT ====="
echo "host: $(hostname)   date: $(date -Is)"
echo "cpus: $(nproc)   total RAM: $(free -m | awk '/Mem:/{print $2" MB"}')"
[ "$HAVE_GPU" = 1 ] && nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
echo "input size: $(du -h "$INPUT" | cut -f1)"
echo "--- cluster/pool free resources ---"
command -v condor_status >/dev/null 2>&1 && condor_status -total 2>&1 | head -20 || echo "condor_status not available on worker"
disk_report "start"

# 1. Check the file format and convert to PNG pages
echo "Checking/converting input: $INPUT"
mkdir -p pages raw
step "1_convert" python3 "$CLUSTER_SIDE/convert.py" "$INPUT" pages

pages=(pages/page_*.png)
if [ ${#pages[@]} -eq 0 ]; then
    echo "No pages were produced from $INPUT" >&2
    exit 1
fi
echo "pages produced: ${#pages[@]}   size of pages/: $(du -sh pages | cut -f1)"
disk_report "after convert"

# 2. Run the model on each page
for page in "${pages[@]}"; do
    name=$(basename "$page" .png)
    echo "Running model on $name"
    step "2_inference_$name" python3 "$CLUSTER_SIDE/inference.py" "$page" "raw/${name}.txt"
done
echo "size of raw/: $(du -sh raw | cut -f1)"
disk_report "after inference"

# 3. Concatenate
echo "Concatenating output"
step "3_concatenate" python3 "$CLUSTER_SIDE/concatenate.py" raw/*.txt "$STEM.txt"

# 4. Serialize
echo "Serializing output"
step "4_serialize" python3 "$CLUSTER_SIDE/serialize.py" "$STEM.txt" "$STEM.json"

# ---------- summary ----------
disk_report "end"
echo "===== SUMMARY ====="
echo "total wall time: $(echo "$(date +%s.%N) - $JOB_START" | bc) s"
echo "outputs: $(du -h "$STEM.txt" "$STEM.json" | tr '\n' ' ')"
echo "Done: $STEM.txt, $STEM.json"