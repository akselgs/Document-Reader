#!/usr/bin/env python3
"""Concatenate the per-page model outputs into one file.

Usage: python3 serialize.py <page_1.txt> [<page_2.txt> ...] <output_file>

The last argument is the output; all earlier arguments are inputs, joined
in the order given.
"""
import sys


def main():
    if len(sys.argv) < 3:
        sys.exit("Usage: serialize.py <input_files...> <output_file>")
    *inputs, output = sys.argv[1:]

    with open(output, "w", encoding="utf-8") as out:
        for path in inputs:
            with open(path, encoding="utf-8") as f:
                text = f.read()
            out.write(text)
            if not text.endswith("\n"):
                out.write("\n")

    print(f"Wrote {len(inputs)} page(s) to {output}")


if __name__ == "__main__":
    main()