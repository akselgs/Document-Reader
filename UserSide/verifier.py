#!/usr/bin/env python3
"""Compare a parser output JSON against a ground-truth JSON, field by field.

Usage: python compare_json.py output.json truth.json
Exit code 0 if every field matches, 1 otherwise.
"""
import json
import sys


def load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def same(a, b):
    # bool is an int subclass in Python: keep True != 1 and False != 0
    if isinstance(a, bool) != isinstance(b, bool):
        return False
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return a == b
    if isinstance(a, str) and isinstance(b, str):
        return a.strip().lower() == b.strip().lower()
    return a == b


def compare(output, truth):
    """Return list of (field, status, got, expected)."""
    results = []
    for key in truth:
        exp = truth[key]
        if key not in output:
            results.append((key, "MISSING", None, exp))
        elif same(output[key], exp):
            results.append((key, "OK", output[key], exp))
        else:
            results.append((key, "WRONG", output[key], exp))
    for key in output:
        if key not in truth:
            results.append((key, "EXTRA", output[key], None))
    return results


def main():
    if len(sys.argv) != 3:
        sys.exit("Usage: python compare_json.py output.json truth.json")
    results = compare(load(sys.argv[1]), load(sys.argv[2]))

    for key, status, got, exp in results:
        if status == "OK":
            print(f"  OK     {key}")
        else:
            print(f"  {status:<6} {key}: got {got!r}, expected {exp!r}")

    checked = [r for r in results if r[1] != "EXTRA"]
    ok = sum(1 for r in checked if r[1] == "OK")
    print(f"\n{ok}/{len(checked)} fields match ({100 * ok / max(len(checked), 1):.0f}%)")
    sys.exit(0 if ok == len(checked) and len(checked) == len(results) else 1)


if __name__ == "__main__":
    main()