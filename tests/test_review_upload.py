import io
import contextlib
import hashlib
import re
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import review  # noqa: E402
import upload  # noqa: E402

GOOD = REPO / "tests" / "fixtures" / "good.jsonl"
BAD = REPO / "tests" / "fixtures" / "bad.jsonl"


def _capture(fn, args):
    buf = io.StringIO()
    err = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(err):
        rc = fn(args)
    return rc, buf.getvalue(), err.getvalue()


@pytest.fixture
def root(tmp_path):
    """A throwaway repo root: tests never touch the real tasks/ or REVIEWED.md."""
    (tmp_path / "tasks").mkdir()
    (tmp_path / "README.md").write_text("# card\n", encoding="utf-8")
    return tmp_path


def _args(root, *extra):
    return ["--repo", "keppy/evalroute-tasks", "--root", str(root), *extra]


def test_review_prints_rows_and_sha():
    rc, out, err = _capture(review.main, [str(GOOD)])
    assert rc == 0
    assert out.startswith("1. [routine-coding] ")
    assert "2. [long-doc-reading]" in out
    m = re.search(r"batch sha256: ([0-9a-f]{64})", out)
    assert m
    assert "add `reviewed:" in out
    assert hashlib.sha256(GOOD.read_bytes()).hexdigest() == m.group(1)


def test_review_bad_usage():
    rc, _, err = _capture(review.main, [])
    assert rc == 2


def test_upload_refuses_without_reviewed(root):
    (root / "tasks" / "keppy.jsonl").write_bytes(GOOD.read_bytes())
    rc, out, err = _capture(upload.main, _args(root, "--dry-run"))
    assert rc == 2
    assert "REFUSED: keppy.jsonl" in err


def test_upload_dry_run_and_real(root, monkeypatch):
    sha = hashlib.sha256(GOOD.read_bytes()).hexdigest()
    (root / "REVIEWED.md").write_text(f"reviewed: {sha}  2026-10-05  keppy\n")
    (root / "tasks" / "keppy.jsonl").write_bytes(GOOD.read_bytes())

    rc, out, err = _capture(upload.main, _args(root, "--dry-run"))
    assert rc == 0, err
    assert "would upload" in out
    assert "keppy.jsonl" in out
    assert "dry run: stopping before upload" in out

    # real path with a fake HfApi injected via sys.modules — no network
    fake = ModuleType("huggingface_hub")
    calls = {}

    class FakeApi:
        def upload_folder(self, **kw):
            calls["folder"] = kw

        def upload_file(self, **kw):
            calls["file"] = kw

    fake.HfApi = FakeApi
    monkeypatch.setitem(sys.modules, "huggingface_hub", fake)
    rc, out, err = _capture(upload.main, _args(root))
    assert rc == 0, err
    assert calls["folder"]["repo_id"] == "keppy/evalroute-tasks"
    assert calls["folder"]["repo_type"] == "dataset"
    assert calls["folder"]["path_in_repo"] == "tasks"
    assert calls["folder"]["folder_path"] == str(root / "tasks")
    assert calls["file"]["path_in_repo"] == "README.md"


def test_upload_validates_first(root):
    bad_sha = hashlib.sha256(BAD.read_bytes()).hexdigest()
    (root / "REVIEWED.md").write_text(f"reviewed: {bad_sha}  2026-10-05  keppy\n")
    (root / "tasks" / "keppy.jsonl").write_bytes(BAD.read_bytes())
    rc, out, err = _capture(upload.main, _args(root, "--dry-run"))
    assert rc == 2
    assert "validate failed" in err


def test_real_batch_is_reviewed_if_present():
    """Every tasks/*.jsonl in the repo must have its sha in REVIEWED.md — the attestation
    travels with the data. (Also guards the defect v0.1.0's tests had: they deleted the batch.)"""
    files = sorted((REPO / "tasks").glob("*.jsonl"))
    shas = upload.reviewed_shas(REPO / "REVIEWED.md")
    for f in files:
        assert upload.sha_of(f) in shas, f"{f.name} is not reviewed"


def test_reviewed_md_is_tracked_not_ignored():
    """REVIEWED.md is the public attestation that a batch was read; it ships in the repo."""
    gi = (REPO / ".gitignore").read_text(encoding="utf-8").split()
    assert "REVIEWED.md" not in gi
    assert "private_terms.txt" in gi
