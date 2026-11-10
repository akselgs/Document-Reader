#!/usr/bin/env python3
"""Compare a parser output JSON against a ground-truth JSON, field by field.

Nested objects are flattened to dotted paths, so every leaf field is scored
individually, e.g. "lysmikroskop.glomeruli" or
"elektronmikroskop.toluidinblått.kortex".

Usage: python compare_json.py output.json truth.json
Exit code 0 if every field matches, 1 otherwise.
"""
import json
import sys
from collections import defaultdict


def load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def flatten(obj, prefix=""):
    """Nested dicts -> {"a.b.c": leaf}. Lists and scalars are leaves."""
    flat = {}
    for key, val in obj.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(val, dict):
            flat.update(flatten(val, path))
        else:
            flat[path] = val
    return flat


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
    """Return list of (field, status, got, expected) over flattened fields."""
    out, tru = flatten(output), flatten(truth)
    results = []
    for key, exp in tru.items():
        if key not in out:
            results.append((key, "MISSING", None, exp))
        elif same(out[key], exp):
            results.append((key, "OK", out[key], exp))
        else:
            results.append((key, "WRONG", out[key], exp))
    for key, got in out.items():
        if key not in tru:
            results.append((key, "EXTRA", got, None))
    return results


def section_of(field):
    """Top-level section name; header fields (no dot) group under 'header'."""
    return field.split(".", 1)[0] if "." in field else "header"


def main():
    if len(sys.argv) != 3:
        sys.exit("Usage: python compare_json.py output.json truth.json")
    results = compare(load(sys.argv[1]), load(sys.argv[2]))

    for key, status, got, exp in results:
        if status == "OK":
            print(f"  OK      {key}")
        else:
            print(f"  {status:<7} {key}: got {got!r}, expected {exp!r}")

    # Per-section tally (EXTRA fields are not scored)
    tally = defaultdict(lambda: [0, 0])  # section -> [ok, total]
    for key, status, _, _ in results:
        if status == "EXTRA":
            continue
        sec = section_of(key)
        tally[sec][1] += 1
        if status == "OK":
            tally[sec][0] += 1

    print("\nPer section:")
    for sec, (ok, total) in tally.items():
        print(f"  {sec:<24} {ok}/{total} ({100 * ok / total:.0f}%)")

    checked = [r for r in results if r[1] != "EXTRA"]
    ok = sum(1 for r in checked if r[1] == "OK")
    print(f"\nTotal: {ok}/{len(checked)} fields match "
          f"({100 * ok / max(len(checked), 1):.0f}%)")
    extras = len(results) - len(checked)
    if extras:
        print(f"{extras} extra field(s) in output not present in truth")
    sys.exit(0 if ok == len(checked) and extras == 0 else 1)


if __name__ == "__main__":
    main()