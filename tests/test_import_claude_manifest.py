"""Claude's export in parts (IMPORT-MANIFEST-1, 2026-11-24): the manifest, the conversations zip,
the parts that hold no chats. Synthetic data only, built from the fields seen in a member's sitting
(version, batches of batch_index, export_url, category, part, filename). The layouts inside the new
conversations zip are assumed (no public description): the old conversations.json, shards
conversations-000.json, one conversation per line (.jsonl), and the part zips zipped together.

Created 2026-11-24.
"""
import io
import json
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

from tests.test_import_chats import claude_export
from tests.test_import_chats_route import _post, _zip, env  # noqa: F401  (env is the route fixture)
from api import chat_import

ROOT = Path(__file__).resolve().parents[1]
ic = chat_import.tool()


def manifest(*extra):
    return {"version": "1.0", "batches": [
        {"batch_index": 0, "category": "frames", "part": 0, "filename": "frames-000.zip",
         "export_url": "https://claude.ai/api/export/abc/frames-000.zip?sig=x"},
        {"batch_index": 1, "category": "conversations", "part": 0, "filename": "conversations-000.zip",
         "export_url": "https://claude.ai/api/export/abc/conversations-000.zip?sig=y"},
        *extra]}


def _zip_bytes(files):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in files.items():
            z.writestr(name, data if isinstance(data, (bytes, str)) else json.dumps(data))
    return buf.getvalue()


# ── the reader ──

def test_manifest_is_recognised_links_only_on_claude_ai():
    info = ic.claude_manifest(manifest(
        {"batch_index": 2, "category": "conversations", "part": 1, "filename": "conversations-001.zip",
         "export_url": "https://evil.example/conversations-001.zip"},
        {"batch_index": 3, "category": "conversations", "part": 2, "filename": "conversations-002.zip",
         "export_url": "http://claude.ai/plain-http.zip"}))
    assert [c["filename"] for c in info["conversations"]] == ["conversations-000.zip", "conversations-001.zip",
                                                             "conversations-002.zip"]
    assert info["conversations"][0]["url"].startswith("https://claude.ai/")
    assert info["conversations"][1]["url"] == "" and info["conversations"][2]["url"] == ""
    assert info["other"] == ["frames"]
    assert ic.claude_manifest({"batches": []}) is None
    assert ic.claude_manifest({"nothing": "here"}) is None
    assert ic.claude_manifest({"batches": [{"x": 1}]}) is None


def test_manifest_file_raises_with_the_downloads(tmp_path):
    f = tmp_path / "manifest.json"
    f.write_text(json.dumps(manifest()))
    with pytest.raises(ic.ClaudeManifest) as e:
        ic.prep(f, tmp_path / "out")
    assert e.value.info["conversations"][0]["filename"] == "conversations-000.zip"


@pytest.mark.parametrize("inner", [
    {"conversations.json": claude_export()},
    {"conversations-000.json": claude_export()},
    {"data/conversations.jsonl": "\n".join(json.dumps(c) for c in claude_export())},
    {"chats/one.json": claude_export()[0]},
])
def test_new_conversations_zip_layouts(tmp_path, inner):
    z = tmp_path / "conversations-000.zip"
    z.write_bytes(_zip_bytes(inner))
    rows = ic.prep(z, tmp_path / "out")
    assert [r["source"] for r in rows if r["kind"] == "conversation"] == ["claude"]


def test_bare_jsonl_of_claude_conversations(tmp_path):
    f = tmp_path / "conversations.jsonl"
    f.write_text("\n".join(json.dumps(c) for c in claude_export()))
    rows = ic.prep(f, tmp_path / "out")
    assert len(rows) == 1 and rows[0]["source"] == "claude"


def test_parts_zipped_together_read_conversations_ignore_frames(tmp_path):
    outer = _zip_bytes({
        "conversations-000.zip": _zip_bytes({"conversations.json": claude_export()}),
        "frames-000.zip": _zip_bytes({"frames.json": [{"frame": 1}]}),
        "manifest.json": manifest(),
    })
    z = tmp_path / "export.zip"
    z.write_bytes(outer)
    notes = {}
    rows = ic.prep(z, tmp_path / "out", notes=notes)
    assert len(rows) == 1 and rows[0]["source"] == "claude"
    assert notes["ignored"] == ["frames-000.zip"]


def test_old_export_unchanged(tmp_path):
    z = tmp_path / "data.zip"
    z.write_bytes(_zip_bytes({"conversations.json": claude_export(), "users.json": [{"uuid": "u"}]}))
    notes = {}
    assert len(ic.prep(z, tmp_path / "out", notes=notes)) == 1 and notes["ignored"] == []


# ── the route ──

def test_route_manifest_answers_with_next_step_and_links(env):  # noqa: F811
    r = _post(env, json.dumps(manifest()).encode(), name="manifest.json")
    assert r.status_code == 400
    j = r.json()
    assert "Claude's list of downloads" in j["error"]["message"]
    assert "conversations-000.zip" in j["error"]["message"]
    imp = j["error"]["details"]["import"]
    assert imp["code"] == "claude_manifest"
    assert imp["conversations"][0]["url"].startswith("https://claude.ai/")
    assert "No conversations found" not in r.text
    assert env.proposals == []


def test_route_frames_part_says_drop_conversations(env):  # noqa: F811
    r = _post(env, _zip_bytes({"frames.json": [{"frame": 1}]}), name="frames-000.zip")
    assert r.status_code == 400
    imp = r.json()["error"]["details"]["import"]
    assert imp == {"code": "claude_part", "category": "frames", "filename": "frames-000.zip"}
    assert env.proposals == []


def test_route_conversations_zip_comes_in(env):  # noqa: F811
    r = _post(env, _zip_bytes({"conversations.json": claude_export()}), name="conversations-000.zip")
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["sources"] == ["claude"] and j["proposed"] == 1 and j["ignored"] == []


def test_route_other_400s_keep_their_shape(env):  # noqa: F811
    r = _post(env, _zip(**{"users.json": [{"uuid": "x"}]}))
    assert r.status_code == 400 and "No conversations" in r.text
    assert "import" not in (r.json()["error"].get("details") or {})


# ── the card's reading of the answer (ui/lib/moveIn.js under node) ──

def _node(script):
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")
    r = subprocess.run([node, "-e", "const m=require('./moveIn.js');" + script], capture_output=True, text=True,
                       timeout=30, cwd=str(ROOT / "ui" / "lib"))
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_card_reads_manifest_answer_in_both_languages():
    env_json = json.dumps({"error": {"message": "x", "details": {"import": {
        "code": "claude_manifest", "conversations": [
            {"filename": "conversations-000.zip", "url": "https://claude.ai/a.zip"},
            {"filename": "conversations-001.zip", "url": "javascript:alert(1)"}]}}}})
    out = _node(f"const j={env_json};console.log(JSON.stringify([m.importAnswer(j,m.moveWords('en')),"
                f"m.importAnswer(j,m.moveWords('ru')),m.importAnswer({{detail:'plain'}},m.moveWords('en')),"
                f"m.importAnswer({{error:{{message:'',details:{{import:{{code:'claude_part',category:'frames',filename:'frames-000.zip'}}}}}}}},m.moveWords('en'))]))")
    en, ru, plain, part = out
    assert en["message"].startswith("This is Claude's list of downloads")
    assert "conversations-000.zip, conversations-001.zip" in en["message"]
    assert en["links"] == [{"name": "conversations-000.zip", "url": "https://claude.ai/a.zip"}]
    assert en["noLink"]  # one part had no claude.ai link: point at the email
    assert ru["message"].startswith("Это список загрузок Claude")
    assert plain == {"message": "plain", "code": "", "links": []}
    assert "frames part" in part["message"] and "conversations-000.zip" in part["message"]
