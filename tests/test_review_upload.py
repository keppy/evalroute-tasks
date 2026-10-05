import io
import contextlib
import re
import sys
from pathlib import Path
from types import ModuleType

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import review  # noqa: E402
import upload  # noqa: E402

GOOD = REPO / "tests" / "fixtures" / "good.jsonl"
BAD = REPO / "tests" / "fixtures" / "bad.jsonl"
REVIEWED = REPO / "REVIEWED.md"


def _capture(fn, args):
    buf = io.StringIO()
    err = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(err):
        rc = fn(args)
    return rc, buf.getvalue(), err.getvalue()


def test_review_prints_rows_and_sha():
    rc, out, err = _capture(review.main, [str(GOOD)])
    assert rc == 0
    assert out.startswith("1. [routine-coding] ")
    assert "2. [long-doc-reading]" in out
    m = re.search(r"batch sha256: ([0-9a-f]{64})", out)
    assert m
    assert "add `reviewed:" in out
    import hashlib
    assert hashlib.sha256(GOOD.read_bytes()).hexdigest() == m.group(1)


def test_review_bad_usage():
    rc, _, err = _capture(review.main, [])
    assert rc == 2


def test_upload_refuses_without_reviewed(monkeypatch):
    REVIEWED.unlink(missing_ok=True)
    rc, out, err = _capture(upload.main, ["--repo", "keppy/evalroute-tasks", "--dry-run"])
    assert rc == 2


def test_upload_dry_run_and_real(monkeypatch):
    import hashlib
    sha = hashlib.sha256(GOOD.read_bytes()).hexdigest()
    REVIEWED.write_text(f"reviewed: {sha}  2026-10-05  keppy\n")
    tasks_dir = REPO / "tasks"
    probe = tasks_dir / "keppy.jsonl"
    probe.write_bytes(GOOD.read_bytes())
    try:
        rc, out, err = _capture(upload.main, ["--repo", "keppy/evalroute-tasks", "--dry-run"])
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
        rc, out, err = _capture(upload.main, ["--repo", "keppy/evalroute-tasks"])
        assert rc == 0, err
        assert calls["folder"]["repo_id"] == "keppy/evalroute-tasks"
        assert calls["folder"]["repo_type"] == "dataset"
        assert calls["folder"]["path_in_repo"] == "tasks"
        assert calls["file"]["path_in_repo"] == "README.md"
    finally:
        probe.unlink(missing_ok=True)
        REVIEWED.unlink(missing_ok=True)


def test_upload_validates_first(monkeypatch):
    import hashlib
    bad_sha = hashlib.sha256(BAD.read_bytes()).hexdigest()
    REVIEWED.write_text(f"reviewed: {bad_sha}  2026-10-05  keppy\n")
    tasks_dir = REPO / "tasks"
    probe = tasks_dir / "keppy.jsonl"
    probe.write_bytes(BAD.read_bytes())
    try:
        rc, out, err = _capture(upload.main, ["--repo", "keppy/evalroute-tasks", "--dry-run"])
        assert rc == 2
        assert "validate failed" in err
    finally:
        probe.unlink(missing_ok=True)
        REVIEWED.unlink(missing_ok=True)
