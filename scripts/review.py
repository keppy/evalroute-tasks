#!/usr/bin/env python3
"""Print every row of one JSONL file, numbered, with the batch sha.

Usage: python scripts/review.py tasks/<contributor>.jsonl
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print("usage: review.py <file.jsonl>", file=sys.stderr)
        return 2
    path = Path(argv[0])
    data = path.read_bytes()
    sha = hashlib.sha256(data).hexdigest()
    n = 0
    for raw in data.decode("utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        n += 1
        row = json.loads(line)
        label = row.get("label", "?")
        text = row.get("text", "")
        print(f"{n}. [{label}] {text}")
    print(f"batch sha256: {sha}")
    print(f"add `reviewed: {sha}  <date>  <contributor>` to REVIEWED.md to allow upload")
    return 0


if __name__ == "__main__":
    sys.exit(main())
