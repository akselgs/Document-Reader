#!/usr/bin/env python3
"""Run the model on one page image and write the generated text to a file.

Usage: python3 inference.py <image_path> <output_text_path>
"""
import os
import subprocess
import sys

MODELPATH = "/share/home/student14/model/files/granite-docling-258M-Q8_0.gguf"
MMPROJPATH = "/share/home/student14/model/files/mmproj-granite-docling-258M-Q8_0.gguf"
EXEPATH = "/share/home/student14/model/llama.cpp/build/bin/llama-mtmd-cli"
PROMPT = "Convert this page to docling."

CONTEXT = "4096"       # -c: must cover prompt + image tokens + generated text
MAX_TOKENS = "2048"    # -n: cap on generated tokens
TIMEOUT_S = 3600       # per page; a stuck run fails instead of hanging


def main():
    if len(sys.argv) != 3:
        sys.exit("Usage: inference.py <image_path> <output_text_path>")
    image_path, text_path = sys.argv[1], sys.argv[2]

    threads = len(os.sched_getaffinity(0))  # cores this job may actually use

    cmd = [
        EXEPATH,
        "-m", MODELPATH,
        "--mmproj", MMPROJPATH,
        "--image", image_path,
        "-p", PROMPT,
        "-c", CONTEXT,
        "-n", MAX_TOKENS,
        "-t", str(threads),
        "--temp", "0",
    ]

    # stdout is captured (it holds the generated text); stderr is left alone,
    # so llama.cpp's progress and error messages go straight to the job's
    # error file, live, instead of appearing only when the run ends.
    result = subprocess.run(cmd, stdout=subprocess.PIPE, text=True, timeout=TIMEOUT_S)

    if result.returncode != 0:
        sys.exit(f"llama-mtmd-cli failed with exit code {result.returncode} "
                 f"(see the job's error file for its messages)")

    with open(text_path, "w", encoding="utf-8") as f:
        f.write(result.stdout)
    print(f"Wrote {len(result.stdout)} characters to {text_path}")


if __name__ == "__main__":
    main()