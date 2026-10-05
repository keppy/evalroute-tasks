import json
import subprocess
import sys
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
FIX = REPO / "tests" / "fixtures"
GOOD = FIX / "good.jsonl"
BAD = FIX / "bad.jsonl"


def run_validate(paths, extra=None):
    cmd = [sys.executable, str(REPO / "scripts" / "validate.py")] + [str(p) for p in paths]
    if extra:
        cmd += extra
    return subprocess.run(cmd, capture_output=True, text=True)


def test_good_passes():
    r = run_validate([GOOD])
    assert r.returncode == 0, r.stderr
    assert "ok: 3 rows, 1 files" in r.stdout
    assert "routine-coding=1" in r.stdout
    assert "long-doc-reading=1" in r.stdout
    assert "math-first-principles=1" in r.stdout


def test_bad_fails_with_rule_lines():
    r = run_validate([BAD], extra=["--private-terms", str(FIX / "private_terms.txt")])
    assert r.returncode == 1
    lines = [l for l in r.stderr.strip().splitlines() if l.startswith("FAIL")]
    # rules 1(id),1(unique),2,3,4,5,6,7(tier2 coherence),7(arm),8,9,10,11
    assert len(lines) == 13, lines
    # rule 9/10 lines must not contain row text
    text_frag = "reads the ledger"
    assert not any(text_frag in l for l in lines), lines
    rule_names = []
    for l in lines:
        body = re.sub(r"^FAIL .*?: \S+: ", "", l)  # drop FAIL file:line id:
        rule_names.append(body.split(" — ")[0])
    rule_names = " ".join(rule_names)
    for name in ("id-format", "id-unique", "text-length", "label-lane", "source",
                 "contributor-format", "week", "tier2-coherence", "tier2-arm",
                 "tier3-single", "publish-gate", "denylist", "no-generated"):
        assert name in rule_names, (name, rule_names)


def test_json_mode():
    r = run_validate([BAD], extra=["--json", "--private-terms", str(FIX / "private_terms.txt")])
    assert r.returncode == 1
    out = json.loads(r.stdout)
    assert out["rows"] == 14
    assert out["files"] == 1
    assert len(out["failures"]) == 13


def test_denylist_flag(tmp_path):
    terms = tmp_path / "private_terms.txt"
    terms.write_text("ledger\n")
    # good.jsonl contains the word "ledger" -> denylist must catch it
    r = run_validate([GOOD], extra=["--private-terms", str(terms)])
    assert r.returncode == 1
    assert "private term at index 0" in r.stderr
    assert "keppy:a3f9c1" in r.stderr


def test_contributor_stem_rule(tmp_path):
    # a file whose stem != contributor fails
    f = tmp_path / "other.jsonl"
    row = {"id": "keppy:a1b2c3", "text": "add a CLI verb that reads the ledger and prints per-lane counts",
           "label": "routine-coding", "source": "written", "contributor": "keppy", "week": "2026-W40"}
    f.write_text(json.dumps(row) + "\n")
    r = run_validate([f])
    assert r.returncode == 1
    assert "contributor-file-stem" in r.stderr


def test_publish_gate_catches_forward_slash_drive_paths():
    """A forward-slash drive path is as identifying as a backslash one; batch 1 review found one that slipped."""
    sys.path.insert(0, str(REPO / "scripts"))
    from validate import GATE_RE
    assert any(rx.search("run git -C C:/Users/someone/repo log") for rx in GATE_RE.values())
