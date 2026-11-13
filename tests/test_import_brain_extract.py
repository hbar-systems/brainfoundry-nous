"""scripts/import_brain.py safe_extract (audit 2026-11-13, import-brain-tar-extractall-unfiltered-path-escape):
a handed-over archive never writes outside the stage. Archives are built here, nothing is restored."""
import importlib.util
import io
import json
import tarfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("import_brain", ROOT / "scripts" / "import_brain.py")
IB = importlib.util.module_from_spec(spec)
spec.loader.exec_module(IB)


def _archive(tmp_path, extra):
    p = tmp_path / "a.tar.gz"
    with tarfile.open(p, "w:gz") as tar:
        data = json.dumps({"format": "brainfoundry-brain-export/v1"}).encode()
        ti = tarfile.TarInfo("manifest.json"); ti.size = len(data)
        tar.addfile(ti, io.BytesIO(data))
        for ti, data in extra:
            tar.addfile(ti, io.BytesIO(data) if data is not None else None)
    return p


def _file(name, data=b"x"):
    ti = tarfile.TarInfo(name); ti.size = len(data)
    return ti, data


def _link(name, target, kind=tarfile.SYMTYPE):
    ti = tarfile.TarInfo(name); ti.type = kind; ti.linkname = target
    return ti, None


@pytest.mark.parametrize("extra", [
    [_file("../escape.txt")],
    [_file("/tmp/abs-escape-import-brain.txt")],
    [_link("lnk", "..")] + [_file("lnk/escape.txt")],
    [_link("hard", "/etc/passwd", tarfile.LNKTYPE)],
    [_link("sym", "/etc/passwd")],
])
def test_unsafe_members_refused_before_anything_is_written(tmp_path, extra):
    arc = _archive(tmp_path, extra)
    stage = tmp_path / "stage"
    stage.mkdir()
    with tarfile.open(arc, "r:gz") as tar:
        with pytest.raises(RuntimeError, match="unsafe archive member"):
            IB.safe_extract(tar, stage)
    assert list(stage.iterdir()) == [] and not (tmp_path / "escape.txt").exists()


def test_plain_archive_extracts(tmp_path):
    arc = _archive(tmp_path, [_file("db/rows.jsonl", b"{}\n")])
    stage = tmp_path / "stage"
    stage.mkdir()
    with tarfile.open(arc, "r:gz") as tar:
        IB.safe_extract(tar, stage)
    assert (stage / "manifest.json").is_file() and (stage / "db" / "rows.jsonl").read_bytes() == b"{}\n"
