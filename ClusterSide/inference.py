#!/usr/bin/env python3
"""Run the model on one page image and write the generated text to a file.

Usage: python3 inference.py <image_path> <output_text_path>
"""
import os
import subprocess
import sys
import threading
import time

MODELPATH = "/share/home/student14/model/files/granite-docling-258M-Q8_0.gguf"
MMPROJPATH = "/share/home/student14/model/files/mmproj-granite-docling-258M-Q8_0.gguf"
EXEPATH = "/share/home/student14/model/llama.cpp/build/bin/llama-mtmd-cli"
PROMPT = "Convert this page to docling."

CONTEXT = "4096"
MAX_TOKENS = "2048"
TIMEOUT_S = 3600

# stderr substrings meaning "model is loaded, inference has begun".
# llama.cpp wording varies by version; check your job's error file and adjust.
INFERENCE_MARKERS = ("encoding image", "image slice", "image/slice")
# stderr substrings worth repeating on stdout for easy collection
PERF_KEYS = ("load time", "prompt eval time", "eval time", "total time",
             "encoded in", "decoded", "memory breakdown", "model buffer", "KV buffer")


def rss_mb(pid):
    try:
        with open(f"/proc/{pid}/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) / 1024
    except OSError:
        pass
    return None


def main():
    if len(sys.argv) != 3:
        sys.exit("Usage: inference.py <image_path> <output_text_path>")
    image_path, text_path = sys.argv[1], sys.argv[2]
    threads = len(os.sched_getaffinity(0))

    cmd = [EXEPATH, "-m", MODELPATH, "--mmproj", MMPROJPATH,
           "--image", image_path, "-p", PROMPT,
           "-c", CONTEXT, "-n", MAX_TOKENS, "-t", str(threads), "--temp", "0"]

    t_start = time.monotonic()
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, bufsize=1)

    samples = []                 # (seconds since start, rss MB)
    stop = threading.Event()
    stdout_chunks = []
    perf_lines = []
    marker_time = [None]

    def sampler():
        while not stop.is_set():
            r = rss_mb(proc.pid)
            if r is not None:
                samples.append((time.monotonic() - t_start, r))
            time.sleep(0.1)

    def read_stdout():
        stdout_chunks.append(proc.stdout.read())

    threads_ = [threading.Thread(target=sampler, daemon=True),
                threading.Thread(target=read_stdout, daemon=True)]
    for t in threads_:
        t.start()

    # Echo stderr live (as before) while watching it for the marker and perf lines.
    deadline = t_start + TIMEOUT_S
    for line in proc.stderr:
        sys.stderr.write(line)
        sys.stderr.flush()
        if marker_time[0] is None and any(m in line for m in INFERENCE_MARKERS):
            marker_time[0] = time.monotonic() - t_start
        if any(k in line for k in PERF_KEYS):
            perf_lines.append(line.rstrip())
        if time.monotonic() > deadline:
            proc.kill()
            sys.exit(f"llama-mtmd-cli timed out after {TIMEOUT_S}s")
    proc.wait()
    stop.set()
    for t in threads_:
        t.join(timeout=2)
    total = time.monotonic() - t_start

    out = "".join(stdout_chunks)
    if proc.returncode != 0:
        sys.exit(f"llama-mtmd-cli failed with exit code {proc.returncode} "
                 f"(see the job's error file for its messages)")

    with open(text_path, "w", encoding="utf-8") as f:
        f.write(out)
    print(f"Wrote {len(out)} characters to {text_path}")

    # ---- profile report (stdout) ----
    m = marker_time[0]
    print(f"[INFERENCE.PY] {os.path.basename(image_path)}")
    print(f"  total subprocess wall time: {total:.2f} s")
    if samples:
        print(f"  peak RSS overall:           {max(r for _, r in samples):.1f} MB")
    if m is not None and samples:
        load = [r for t, r in samples if t <= m]
        inf = [r for t, r in samples if t > m]
        print(f"  load phase  (until inference marker): {m:.2f} s, "
              f"peak RSS {max(load) if load else float('nan'):.1f} MB")
        print(f"  infer phase (after marker):           {total - m:.2f} s, "
              f"peak RSS {max(inf) if inf else float('nan'):.1f} MB")
    else:
        print("  (inference marker not seen in stderr; adjust INFERENCE_MARKERS, "
              "or rely on llama.cpp's own timings below)")
    print("  llama.cpp reported:")
    for l in perf_lines:
        print(f"    {l.strip()}")


if __name__ == "__main__":
    main()