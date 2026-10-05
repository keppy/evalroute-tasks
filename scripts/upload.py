#!/usr/bin/env python3
"""Upload the reviewed corpus to a Hugging Face dataset repo.

Usage: python scripts/upload.py --repo <owner/name> [--dry-run] [--root <repo-root>]

Gates:
  - runs scripts/validate.py over <root>/tasks/*.jsonl first; refuses on failure
  - each tasks/<file>.jsonl's sha256 must appear in <root>/REVIEWED.md
Refuses with exit 2 naming the offending file.

--root exists so tests run against a temporary copy and never touch the real
tasks/ and REVIEWED.md (the first version of the tests deleted a reviewed batch).
"""
from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def sha_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def reviewed_shas(reviewed: Path) -> set[str]:
    if not reviewed.exists():
        return set()
    rx = re.compile(r"reviewed:\s*([0-9a-f]{64})")
    return set(rx.findall(reviewed.read_text(encoding="utf-8")))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--root", default=str(REPO_ROOT),
                    help="repo root holding tasks/, REVIEWED.md, README.md (tests point this at a tmp copy)")
    args = ap.parse_args(argv)
    root = Path(args.root)
    reviewed = root / "REVIEWED.md"

    tasks_dir = root / "tasks"
    files = sorted(tasks_dir.glob("*.jsonl"))
    if not files:
        print("nothing to upload: tasks/ holds no .jsonl files", file=sys.stderr)
        return 2

    # gate 1: validate
    v = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "validate.py")] + [str(f) for f in files],
        capture_output=True, text=True)
    if v.returncode != 0:
        print("validate failed; refusing to upload:", file=sys.stderr)
        sys.stderr.write(v.stderr)
        return 2

    # gate 2: REVIEWED.md must carry every file's sha
    shas = reviewed_shas(reviewed)
    missing = [f for f in files if sha_of(f) not in shas]
    if missing:
        for f in missing:
            print(f"REFUSED: {f.name} — no reviewed: {sha_of(f)} line in REVIEWED.md", file=sys.stderr)
        return 2

    if args.dry_run:
        print(f"would upload to {args.repo} (repo_type=dataset):")
        for f in files:
            print(f"  tasks/{f.name}  {f.stat().st_size} bytes  sha {sha_of(f)[:12]}…")
        print("  README.md  (dataset card)")
        print("dry run: stopping before upload")
        return 0

    from huggingface_hub import HfApi

    api = HfApi()
    api.upload_folder(
        folder_path=str(tasks_dir),
        path_in_repo="tasks",
        repo_id=args.repo,
        repo_type="dataset",
        commit_message=f"evalroute-tasks corpus update {datetime.now().isoformat(timespec='seconds')} ({date.today().isoformat()})",
    )
    api.upload_file(
        path_or_fileobj=str(root / "README.md"),
        path_in_repo="README.md",
        repo_id=args.repo,
        repo_type="dataset",
        commit_message="update dataset card",
    )
    print(f"uploaded {len(files)} files + dataset card to {args.repo}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
