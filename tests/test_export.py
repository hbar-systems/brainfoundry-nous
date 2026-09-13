"""Tests for api/export.py (unreleased 0.10.0): the on-box one-command export.

Data sources are injected (no database); the runtime and brain-apps dirs are
redirected to tmp. What matters: v1-compatible layout and manifest, every
non-git state included, and the secret guard (settings.json, .env, audit logs
never land in an archive even if they sit next to exported files).

Created 2026-09-13.
"""
import json
import tarfile

import pytest

from api import export


def _rows(table):
    data = {
        "document_embeddings": [{"document_name": "a.md", "content": "hello", "metadata": {"layer": "semantic"},
                                 "embedding": "[0.1,0.2]", "created_at": "t"}],
        "chat_sessions": [{"session_id": "s1", "model_name": "m", "title": "t", "created_at": "t"}],
        "chat_messages": [{"session_id": "s1", "role": "user", "content": "hi", "created_at": "t"},
                          {"session_id": "s1", "role": "assistant", "content": "yo", "created_at": "t"}],
    }
    return iter(data[table])


def _probe():
    return {"embedding_dim": 1024}


@pytest.fixture(autouse=True)
def _dirs(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime"; runtime.mkdir()
    apps = tmp_path / "brain-apps"; apps.mkdir()
    data = tmp_path / "data"; data.mkdir()
    monkeypatch.setattr(export, "RUNTIME_DIR", runtime)
    monkeypatch.setattr(export, "EXPORTS_DIR", runtime / "exports")
    monkeypatch.setattr(export, "BRAIN_APPS_DIR", apps)
    monkeypatch.setattr(export, "PEERS_PATH", data / "peers.json")
    monkeypatch.setenv("BRAIN_ID", "Test Brain")
    # state that must be exported
    (runtime / "brain_persona.local.md").write_text("# I am test")
    (runtime / "charter.md").write_text("# charter")
    (apps / "installed.json").write_text(json.dumps({"dialect": "brain-apps-installed/v1",
                                                      "apps": [{"id": "daybook"}], "packs": {"base": {}}}))
    (data / "peers.json").write_text("[]")
    # state that must NOT be exported, deliberately placed next to exported files
    (runtime / "settings.json").write_text('{"secret": "x"}')
    (runtime / "tool_audit.jsonl").write_text("{}\n")
    (runtime / ".env").write_text("BRAIN_API_KEY=nope")
    return tmp_path


def _members(path):
    with tarfile.open(path, "r:gz") as tar:
        return {m.name for m in tar.getmembers() if m.isfile()}, tar


def test_build_export_layout_and_manifest(tmp_path):
    out = export.build_export(tmp_path / "out", rows=_rows, probe=_probe)
    assert out.name.startswith("brain-export-test-brain-") and out.name.endswith(".tar.gz")
    with tarfile.open(out, "r:gz") as tar:
        names = {m.name for m in tar.getmembers() if m.isfile()}
        manifest = json.loads(tar.extractfile("manifest.json").read())
        chunks = tar.extractfile("db/document_embeddings.jsonl").read().decode().splitlines()
    assert {"manifest.json", "db/document_embeddings.jsonl", "db/chat_sessions.jsonl",
            "db/chat_messages.jsonl", "persona/brain_persona.local.md", "md/brain_persona.local.md",
            "md/charter.md", "apps/installed.json", "peers/peers.json"} <= names
    assert manifest["format"] == "brainfoundry-brain-export/v1"   # import_brain.py compatible
    assert manifest["embedding"]["dimension"] == 1024
    assert manifest["contents"]["tables"] == {"document_embeddings": 1, "chat_sessions": 1, "chat_messages": 2}
    assert manifest["contents"]["persona"] is True
    assert manifest["contents"]["apps"] == 1
    assert manifest["excludes_secrets"] is True
    assert json.loads(chunks[0])["document_name"] == "a.md"


def test_secrets_never_in_archive(tmp_path):
    out = export.build_export(tmp_path / "out", rows=_rows, probe=_probe)
    with tarfile.open(out, "r:gz") as tar:
        base_names = {m.name.rsplit("/", 1)[-1] for m in tar.getmembers()}
    assert not (base_names & export._NEVER)


def test_guard_refuses_forbidden_member(tmp_path, monkeypatch):
    # Simulate a future regression that copies settings.json into md/: the
    # post-build scan must delete the archive and raise.
    real_copy = export.shutil.copyfile

    def leaky(src, dst):
        real_copy(src, dst)
        if str(dst).endswith("charter.md"):
            real_copy(export.RUNTIME_DIR / "settings.json", dst.parent / "settings.json")
    monkeypatch.setattr(export.shutil, "copyfile", leaky)
    with pytest.raises(RuntimeError, match="forbidden"):
        export.build_export(tmp_path / "out", rows=_rows, probe=_probe)
    assert not list((tmp_path / "out").glob("*.tar.gz"))


def test_empty_brain_exports_fine(tmp_path, monkeypatch):
    for f in ("brain_persona.local.md", "charter.md"):
        (export.RUNTIME_DIR / f).unlink()
    (export.BRAIN_APPS_DIR / "installed.json").unlink()
    export.PEERS_PATH.unlink()
    out = export.build_export(tmp_path / "out", rows=lambda t: iter([]), probe=lambda: {"embedding_dim": None})
    with tarfile.open(out, "r:gz") as tar:
        manifest = json.loads(tar.extractfile("manifest.json").read())
    assert manifest["contents"]["persona"] is False
    assert manifest["contents"]["tables"]["document_embeddings"] == 0


def test_list_and_router_helpers(tmp_path):
    export.build_export(export.EXPORTS_DIR, rows=_rows, probe=_probe)
    items = export.list_exports()
    assert len(items) == 1 and items[0]["size"] > 0
    from fastapi import HTTPException
    with pytest.raises(HTTPException):
        export._resolve("../etc/passwd")
    with pytest.raises(HTTPException):
        export._resolve("brain-export-missing.tar.gz")
    assert export._resolve(items[0]["name"]).is_file()
    assert export.export_delete(items[0]["name"])["deleted"] is True
    assert export.list_exports() == []


def test_cli_writes_archive_to_out_dir(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(export, "_pg_rows", _rows)
    monkeypatch.setattr(export, "_pg_probe", _probe)
    rc = export.main(["--out", str(tmp_path / "cli")])
    assert rc == 0
    files = list((tmp_path / "cli").glob("brain-export-*.tar.gz"))
    assert len(files) == 1
    assert "secrets: excluded" in capsys.readouterr().out
