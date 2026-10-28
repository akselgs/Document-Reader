#!/usr/bin/env python3
"""Make sure the input is a PNG, converting from PDF if needed.

Usage: python3 convert.py <input_file> <output_png>

- PNG -> copied unchanged to the output path
- PDF -> first page rendered to PNG with Ghostscript (gs) at DPI (set below)
- anything else -> rejected (exit code 1)
"""
import shutil
import subprocess
import sys

DPI = 150  # placeholder, resolution not decided yet

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
PDF_MAGIC = b"%PDF-"


def detect_format(path):
    """Detect the type from the file's first bytes, not its extension."""
    with open(path, "rb") as f:
        header = f.read(8)
    if header.startswith(PNG_MAGIC):
        return "png"
    if header.startswith(PDF_MAGIC):
        return "pdf"
    return None


def pdf_to_png(src, dst):
    cmd = [
        "gs",
        "-dBATCH", "-dNOPAUSE", "-dSAFER", "-q",
        "-sDEVICE=png16m",          # 24-bit colour PNG
        f"-r{DPI}",
        "-dFirstPage=1", "-dLastPage=1",   # first page only
        f"-sOutputFile={dst}",
        src,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        sys.exit(f"Ghostscript failed:\n{result.stderr.strip()}")


def main():
    if len(sys.argv) != 3:
        sys.exit("Usage: convert.py <input_file> <output_png>")
    src, dst = sys.argv[1], sys.argv[2]

    fmt = detect_format(src)
    if fmt == "png":
        print("Input is already a PNG")
        shutil.copy(src, dst)
    elif fmt == "pdf":
        print(f"Converting PDF to PNG at {DPI} DPI")
        pdf_to_png(src, dst)
    else:
        sys.exit(f"Rejected: {src} is not a PNG or PDF")


if __name__ == "__main__":
    main()