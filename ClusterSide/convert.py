#!/usr/bin/env python3
"""Make sure the input is one or more PNG pages, converting from PDF if needed.

Usage: python3 convert.py <input_file> <output_dir>

- PNG -> copied unchanged to <output_dir>/page_001.png
- PDF -> first MAX_PAGES pages rendered with Ghostscript (gs) at DPI
         to <output_dir>/page_001.png, page_002.png, ...
- anything else -> rejected (exit code 1)
"""
import glob
import os
import shutil
import subprocess
import sys

DPI = 150  # placeholder, resolution not decided yet
MAX_PAGES = 3

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


def pdf_to_pngs(src, dst_dir):
    cmd = [
        "gs",
        "-dBATCH", "-dNOPAUSE", "-dSAFER", "-q",
        "-sDEVICE=png16m",                           # 24-bit colour PNG
        f"-r{DPI}",
        "-dFirstPage=1", f"-dLastPage={MAX_PAGES}",  # at most MAX_PAGES pages
        f"-sOutputFile={os.path.join(dst_dir, 'page_%03d.png')}",
        src,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        sys.exit(f"Ghostscript failed:\n{result.stderr.strip()}")


def main():
    if len(sys.argv) != 3:
        sys.exit("Usage: convert.py <input_file> <output_dir>")
    src, dst_dir = sys.argv[1], sys.argv[2]
    os.makedirs(dst_dir, exist_ok=True)

    fmt = detect_format(src)
    if fmt == "png":
        print("Input is already a PNG")
        shutil.copy(src, os.path.join(dst_dir, "page_001.png"))
    elif fmt == "pdf":
        print(f"Converting PDF to PNG at {DPI} DPI (max {MAX_PAGES} pages)")
        pdf_to_pngs(src, dst_dir)
    else:
        sys.exit(f"Rejected: {src} is not a PNG or PDF")

    pages = sorted(glob.glob(os.path.join(dst_dir, "page_*.png")))
    if not pages:
        sys.exit("No pages were produced")
    print(f"Produced {len(pages)} page(s)")


if __name__ == "__main__":
    main()