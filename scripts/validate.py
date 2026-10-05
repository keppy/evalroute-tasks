#!/usr/bin/env python3
"""Validate evalroute-tasks JSONL files.

Usage: python scripts/validate.py [--json] [--private-terms FILE] tasks/*.jsonl
Exit 0 on all-good, 1 on any failure.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
LANES_FILE = REPO_ROOT / "schema" / "lanes.txt"
DEFAULT_PRIVATE = REPO_ROOT / "private_terms.txt"

SOURCES = {"ledger-pinned", "ledger-correction", "taskset", "written"}
VERDICTS = {"pass", "fail"}
METHODS = {"measured", "observed"}
TIER3_KEYS = ("checker", "rubric", "reference")
TIER2_KEYS = ("arm", "verdict", "method", "n")
ID_RE = re.compile(r"^[a-z0-9_-]+:[a-z0-9_-]{4,}$")
CONTRIB_RE = re.compile(r"^[a-z0-9_-]+$")
WEEK_RE = re.compile(r"^\d{4}-W\d{2}$")
ARM_RE = re.compile(r"^[^@\s]+@(low|medium|high|xhigh|none)$")

# rule 9: publish gate regexes. name -> compiled pattern.
SECRET_RE = re.compile(
    r"sk-[A-Za-z0-9_-]{8,}|hf_[A-Za-z0-9]{8,}|eyJ[A-Za-z0-9_-]{10,}|ghp_[A-Za-z0-9]{20,}"
)
GATE_RE = {
    "secrets": SECRET_RE,
    "paths": re.compile(r"[A-Za-z]:[\/]|/c/Users|~/|AppData|/home/[a-z]"),
    "email": re.compile(r"\S+@\S+\.\S+"),
    "handles": re.compile(r"(^|\s)@[A-Za-z0-9_]{2,}"),
    "urls-with-credentials": re.compile(r"://[^/\s]+:[^/\s]+@"),
    "hostname-ish": re.compile(r"\b[a-z0-9-]+\.(local|lan|internal)\b"),
}


class Failure:
    def __init__(self, file, lineno, row_id, rule, message, redacted=False):
        self.file, self.lineno, self.row_id = file, lineno, row_id
        self.rule, self.message, self.redacted = rule, message, redacted

    def line(self, text_preview=None):
        tid = self.row_id if self.row_id else "(unparseable)"
        return f"FAIL {self.file}:{self.lineno} {tid}: {self.rule} — {self.message}"

    def as_dict(self, text_preview=None):
        d = {"file": self.file, "line": self.lineno, "id": self.row_id,
             "rule": self.rule, "message": self.message}
        if not self.redacted and text_preview:
            d["text_preview"] = text_preview
        return d


def load_lanes():
    lanes = []
    for line in LANES_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            lanes.append(line)
    if not lanes:
        raise SystemExit("schema/lanes.txt is empty — cannot validate")
    return lanes


def load_private_terms(explicit=None):
    path = Path(explicit) if explicit else DEFAULT_PRIVATE
    if not path.exists():
        return []
    terms = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            terms.append(line)
    return terms


def gate_scan(s):
    """Return list of rule names hit by the publish gate in string s."""
    hits = []
    if SECRET_RE.search(s):
        hits.append("secrets")
    for name, rx in GATE_RE.items():
        if name == "secrets":
            continue
        if rx.search(s):
            hits.append(name)
    return hits


def denylist_scan(s, terms):
    """Return indices (0-based) of whole-word case-insensitive hits."""
    idx = []
    for i, term in enumerate(terms):
        if re.search(r"(?<![A-Za-z0-9_])" + re.escape(term) + r"(?![A-Za-z0-9_])", s, re.IGNORECASE):
            idx.append(i)
    return idx


def check_row(row, file, lineno, lanes, terms, seen_ids, failures):
    def fail(rule, msg, redacted=False):
        failures.append(Failure(file, lineno, row.get("id") if isinstance(row, dict) else None,
                                rule, msg, redacted))

    if not isinstance(row, dict):
        fail("json", "row is not a JSON object", redacted=True)
        return
    row_id = row.get("id")
    text = row.get("text")

    # rule 1
    if not isinstance(row_id, str) or not ID_RE.match(row_id):
        fail("id-format", "id missing or does not match ^[a-z0-9_-]+:[a-z0-9_-]{4,}$")
    else:
        if row_id in seen_ids:
            fail("id-unique", f"id {row_id} appears more than once across files")
        seen_ids.add(row_id)

    # rule 11: generation-shape ids
    if isinstance(row_id, str) and (row_id.startswith("aug:") or row_id.startswith("seed:")):
        fail("no-generated", "id prefix aug:/seed: is not allowed — the corpus never holds paraphrases")

    # rule 2
    if not isinstance(text, str) or len(text) < 12 or len(text) > 2000:
        fail("text-length", "text must be a string of 12..2000 chars")
    elif text.strip() == "":
        fail("text-padding", "text is newline-only padding")
    elif "\n\n" in text.strip() and text.strip("\n") == "":
        fail("text-padding", "text is newline-only padding")

    # rule 3
    label = row.get("label")
    if label not in lanes:
        fail("label-lane", f"label {label!r} is not a lane in schema/lanes.txt")

    # rule 4
    if row.get("source") not in SOURCES:
        fail("source", "source must be one of ledger-pinned|ledger-correction|taskset|written")

    # rule 5
    contrib = row.get("contributor")
    if not isinstance(contrib, str) or not CONTRIB_RE.match(contrib):
        fail("contributor-format", "contributor must match ^[a-z0-9_-]+$")
    else:
        if isinstance(row_id, str) and ID_RE.match(row_id) and row_id.split(":")[0] != contrib:
            fail("contributor-id-prefix", "contributor must equal the id prefix")
        stem = Path(file).stem
        if contrib != stem and Path(file).parent.name != "fixtures":
            fail("contributor-file-stem", f"contributor {contrib!r} must equal the file stem {stem!r}")

    # rule 6
    week = row.get("week")
    if not isinstance(week, str) or not WEEK_RE.match(week):
        fail("week", "week must match ^\\d{4}-W\\d{2}$")

    # rule 7: tier 2 all-or-none
    present = [k for k in TIER2_KEYS if k in row and row[k] is not None]
    if present:
        missing = [k for k in TIER2_KEYS if k not in present]
        if missing:
            fail("tier2-coherence", "tier 2 keys arm/verdict/method/n must all be present together; missing " + ", ".join(missing))
        else:
            if not (isinstance(row["arm"], str) and ARM_RE.match(row["arm"])):
                fail("tier2-arm", "arm must match ^[^@\\s]+@(low|medium|high|xhigh|none)$")
            if row["verdict"] not in VERDICTS:
                fail("tier2-verdict", "verdict must be pass or fail")
            if row["method"] not in METHODS:
                fail("tier2-method", "method must be measured or observed")
            n = row["n"]
            if not isinstance(n, int) or isinstance(n, bool) or n < 1:
                fail("tier2-n", "n must be an integer >= 1")

    # rule 8: tier 3
    nonnull = [k for k in TIER3_KEYS if row.get(k) is not None]
    if len(nonnull) > 1:
        fail("tier3-single", "at most one of checker/rubric/reference may be non-null")
    for k in TIER3_KEYS:
        v = row.get(k)
        if v is not None and (not isinstance(v, str) or len(v) > 4000):
            fail(f"tier3-{k}", f"{k} must be a string of at most 4000 chars when non-null")

    # rule 9: publish gate on text and tier-3 strings
    gate_targets = [("text", text)] + [(k, row[k]) for k in TIER3_KEYS if row.get(k)]
    for field, s in gate_targets:
        if not isinstance(s, str):
            continue
        for hit in gate_scan(s):
            fail("publish-gate", f"{field} hits publish-gate rule {hit}", redacted=True)

    # rule 10: denylist on text and tier-3 strings
    if terms:
        for field, s in gate_targets:
            if not isinstance(s, str):
                continue
            for i in denylist_scan(s, terms):
                fail("denylist", f"{field} hits private term at index {i}", redacted=True)


def validate_files(paths, lanes, terms):
    failures = []
    seen_ids = set()
    rows = 0
    per_lane = {}
    for path in paths:
        p = Path(path)
        with p.open("r", encoding="utf-8") as fh:
            for lineno, raw in enumerate(fh, start=1):
                line = raw.strip()
                if not line:
                    continue
                rows += 1
                try:
                    row = json.loads(line)
                except json.JSONDecodeError as e:
                    failures.append(Failure(p.name, lineno, None, "json", f"invalid JSON: {e.msg}"))
                    continue
                before = len(failures)
                check_row(row, str(p), lineno, lanes, terms, seen_ids, failures)
                # count good rows per lane for the ok summary
                if len(failures) == before and isinstance(row, dict) and row.get("label") in lanes:
                    per_lane[row["label"]] = per_lane.get(row["label"], 0) + 1
    return rows, per_lane, failures


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="*", help="tasks/*.jsonl (empty = all tasks/*.jsonl)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--private-terms", default=None)
    args = ap.parse_args(argv)

    lanes = load_lanes()
    terms = load_private_terms(args.private_terms)
    paths = [Path(f) for f in args.files]
    if not paths:
        tasks_dir = REPO_ROOT / "tasks"
        paths = sorted(tasks_dir.glob("*.jsonl"))

    rows, per_lane, failures = validate_files(paths, lanes, terms)

    if args.json:
        out = {
            "rows": rows,
            "files": len(paths),
            "per_lane": per_lane,
            "failures": [f.as_dict() for f in failures],
        }
        print(json.dumps(out, indent=2))
    else:
        for f in failures:
            print(f.line(), file=sys.stderr)

    if failures:
        return 1
    lane_str = " ".join(f"{k}={v}" for k, v in sorted(per_lane.items()))
    print(f"ok: {rows} rows, {len(paths)} files, per lane: {lane_str}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
