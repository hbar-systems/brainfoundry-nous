"""Other AIs through the same import (scripts/import_chats.py, 2026-11-16): Gemini
(Takeout My Activity, json and html), DeepSeek, Grok, Copilot (csv), Le Chat, and the
pasted fallback (text, markdown, html, pdf). Synthetic fixtures only, shaped after the
descriptions named in import_chats.FORMATS; no real export is read.

Created 2026-11-16.
"""
import csv
import importlib.util
import io
import json
import pathlib
import zipfile

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("import_chats_ai", ROOT / "scripts" / "import_chats.py")
ic = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ic)


# ── fixtures ──────────────────────────────────────────────────────────────

def gemini_activity():
    """MyActivity.json records in the three shapes described: title 'Prompted ...' with
    safeHtmlItem, details Request/Response, and userInteractions with serialized json."""
    url = "https://gemini.google.com/app/c/abc123def456"
    return [
        {"header": "Gemini Apps", "title": "Prompted How far is the moon?", "titleUrl": url,
         "time": "2025-03-01T10:00:00.000Z", "products": ["Gemini Apps"],
         "safeHtmlItem": [{"html": "<p>About <b>384,400 km</b>.</p><ul><li>on average</li></ul>"}]},
        {"header": "Gemini", "title": "Used Gemini Apps", "titleUrl": url, "time": "2025-03-01T10:02:00Z",
         "products": ["Gemini Apps"],
         "details": [{"name": "Request", "value": "And the sun?"}, {"name": "Response", "value": "About 150 million km."}]},
        # no conversation id: grouped by the 30 minute gap
        {"header": "Gemini", "title": "Used Gemini Apps", "time": "2025-04-02T09:00:00Z", "products": ["Gemini Apps"],
         "userInteractions": [{"userInteraction": {"endpoint": 2,
                                                   "request": json.dumps([{"text": "Name a red fruit"}]),
                                                   "response": json.dumps([{"text": "A cherry."}])}}]},
        {"header": "Gemini Apps", "title": "Prompted And a yellow one?", "time": "2025-04-02T09:10:00Z",
         "products": ["Gemini Apps"], "safeHtmlItem": [{"html": "<p>A banana.</p>"}]},
        {"header": "Gemini Apps", "title": "Prompted Weather tomorrow?", "time": "2025-04-02T12:00:00Z",
         "products": ["Gemini Apps"], "safeHtmlItem": [{"html": "<p>Sunny.</p>"}]},
        # a full My Activity export carries other products: they stay outside
        {"header": "Search", "title": "Searched for private thing", "time": "2025-04-02T09:05:00Z",
         "products": ["Search"]},
    ]


GEMINI_HTML = """<html><body><div class="mdl-grid">
<div class="outer-cell mdl-cell mdl-cell--12-col mdl-shadow--2dp"><div class="mdl-grid">
<div class="header-cell mdl-cell mdl-cell--12-col"><p class="mdl-typography--title">Gemini Apps<br></p></div>
<div class="content-cell mdl-cell mdl-cell--6-col mdl-typography--body-1">Prompted Write a haiku about rain<br>Mar 5, 2025, 8:15:00 PM CET<br><p>Soft rain on the roof,</p><p>the city hums low.</p></div>
<div class="content-cell mdl-cell mdl-cell--12-col mdl-typography--caption"><b>Products:</b><br>&emsp;Gemini Apps<br></div>
</div></div>
<div class="outer-cell mdl-cell mdl-cell--12-col mdl-shadow--2dp"><div class="mdl-grid">
<div class="header-cell mdl-cell mdl-cell--12-col"><p class="mdl-typography--title">Gemini Apps<br></p></div>
<div class="content-cell mdl-cell mdl-cell--6-col mdl-typography--body-1">Prompted Make it sadder<br>Mar 5, 2025, 8:16:00 PM CET<br><p>Grey rain, empty street.</p></div>
<div class="content-cell mdl-cell mdl-cell--12-col mdl-typography--caption"><b>Products:</b><br>&emsp;Gemini Apps<br></div>
</div></div>
<div class="outer-cell mdl-cell mdl-cell--12-col mdl-shadow--2dp"><div class="mdl-grid">
<div class="header-cell mdl-cell mdl-cell--12-col"><p class="mdl-typography--title">Search<br></p></div>
<div class="content-cell mdl-cell mdl-cell--6-col mdl-typography--body-1">Searched for Gemini secrets<br>Mar 5, 2025, 8:17:00 PM CET<br></div>
</div></div>
</div></body></html>"""


def deepseek_export():
    """mapping tree with fragments; the first answer was regenerated (r1 abandoned)."""
    t = "2025-02-10T08:00:00+08:00"
    return [{"id": "ds-0001-aaaa", "title": "Primes", "inserted_at": t, "updated_at": "2025-02-10T08:05:00+08:00",
             "mapping": {
                 "root": {"id": "root", "parent": None, "children": ["1"], "message": None},
                 "1": {"id": "1", "parent": "root", "children": ["2", "3"], "message": {
                     "inserted_at": t, "model": "deepseek-chat",
                     "fragments": [{"type": "REQUEST", "content": "Is 91 prime?"}]}},
                 "2": {"id": "2", "parent": "1", "children": [], "message": {
                     "inserted_at": "2025-02-10T08:00:05+08:00",
                     "fragments": [{"type": "RESPONSE", "content": "OLD DEEPSEEK ANSWER"}]}},
                 "3": {"id": "3", "parent": "1", "children": [], "message": {
                     "inserted_at": "2025-02-10T08:00:09+08:00", "model": "deepseek-reasoner",
                     "fragments": [{"type": "THINK", "content": "SECRET REASONING"},
                                   {"type": "RESPONSE", "content": "No: 91 = 7 x 13."}]}},
             }}]


def _bson(ms):
    return {"$date": {"$numberLong": str(ms)}}


def grok_export():
    """prod-grok-backend.json: conversations with responses linked by parent_response_id."""
    t = 1738404000000  # 2025-02-01
    return {"conversations": [{
        "conversation": {"id": "grok-conv-0001", "title": "Rust or Go", "create_time": "2025-02-01T10:00:00Z",
                         "modify_time": "2025-02-01T10:05:00Z", "user_id": "u-1", "starred": False},
        "responses": [
            {"response": {"_id": "r1", "parent_response_id": None, "sender": "human",
                          "message": "Rust or Go for a CLI?", "create_time": _bson(t)}, "share_link": {}},
            {"response": {"_id": "r2", "parent_response_id": "r1", "sender": "ASSISTANT",
                          "message": "OLD GROK ANSWER", "create_time": _bson(t + 5000), "model": "grok-3"}},
            {"response": {"_id": "r3", "parent_response_id": "r1", "sender": "grok-3",
                          "message": "Go, for the fast start.", "create_time": _bson(t + 9000), "model": "grok-3"}},
        ]}], "projects": [], "tasks": []}


def copilot_csv():
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Conversation", "Time", "Author", "Message"])
    w.writerow(["Trip to Lisbon", "2025-05-01T09:00:00", "Human", "Plan three days in Lisbon"])
    w.writerow(["Trip to Lisbon", "2025-05-01T09:00:20", "AI", "Day 1: Alfama, Day 2: Belem, Day 3: Sintra."])
    w.writerow(["Sourdough", "2025-05-03T18:00:00", "Human", "Why is my bread flat?"])
    w.writerow(["Sourdough", "2025-05-03T18:00:15", "AI", "The starter may be weak."])
    return ("﻿" + buf.getvalue()).encode("utf-8")


def copilot_chat_csv():
    return ("CreatedAt,MessageContent,Author,ChatName\n"
            "5/6/2025 10:00:00 +02:00,Summarise this memo,User,Memo\n"
            "5/6/2025 10:00:09 +02:00,The memo asks for a budget.,Copilot,Memo\n").encode("utf-8")


def lechat_export():
    return [{"id": "lc-77770000", "title": "French verbs", "created_at": "2025-06-01T12:00:00Z",
             "chat_messages": [
                 {"role": "user", "content": "Conjugate aller", "created_at": "2025-06-01T12:00:00Z"},
                 {"role": "assistant", "content": [{"type": "text", "text": "je vais, tu vas, il va"}],
                  "created_at": "2025-06-01T12:00:03Z"}]}]


def _zip(path, files):
    with zipfile.ZipFile(path, "w") as z:
        for name, data in files.items():
            z.writestr(name, data if isinstance(data, (bytes, str)) else json.dumps(data))
    return path


def _prep(tmp_path, src, **kw):
    rows = ic.prep(src, tmp_path / "out", **kw)
    convs = [r for r in rows if r["kind"] == "conversation"]
    return convs, {r["id"]: (tmp_path / "out" / r["file"]).read_text(encoding="utf-8") for r in convs}


# ── Gemini ────────────────────────────────────────────────────────────────

def test_gemini_takeout_zip_groups_by_conversation_id_then_gap(tmp_path):
    src = _zip(tmp_path / "takeout-20251116.zip", {
        "Takeout/My Activity/Gemini Apps/MyActivity.json": gemini_activity(),
        "Takeout/archive_browser.html": "<html></html>"})
    convs, docs = _prep(tmp_path, src)
    assert {r["source"] for r in convs} == {"gemini"}
    # one by id (2 records), then gap groups: 09:00 + 09:10 together, 12:00 alone
    assert sorted(int(r["turns"]) for r in convs) == [2, 4, 4]
    moon = docs["abc123def456"]
    assert moon.startswith("# How far is the moon?\n")
    assert "## Me, 2025-03-01T10:00:00Z\n\nHow far is the moon?" in moon
    assert "## Assistant (Gemini), 2025-03-01T10:00:00Z\n\nAbout 384,400 km." in moon
    assert "And the sun?" in moon and "About 150 million km." in moon
    fruit = next(t for t in docs.values() if "red fruit" in t)
    assert "A cherry." in fruit and "A banana." in fruit and "Sunny." not in fruit
    assert not any("private thing" in t for t in docs.values())
    r = next(r for r in convs if r["id"] == "abc123def456")
    assert r["file"] == "docs/gemini_2025-03-01_how-far-is-the-moon_abc123de.md"


def test_gemini_bare_json_file(tmp_path):
    src = tmp_path / "MyActivity.json"
    src.write_text(json.dumps(gemini_activity()))
    convs, _ = _prep(tmp_path, src)
    assert len(convs) == 3


def test_gemini_html(tmp_path):
    src = tmp_path / "MyActivity.html"
    src.write_text(GEMINI_HTML, encoding="utf-8")
    convs, docs = _prep(tmp_path, src)
    assert len(convs) == 1 and convs[0]["source"] == "gemini" and convs[0]["date"] == "2025-03-05"
    t = next(iter(docs.values()))
    assert "## Me, 2025-03-05T20:15:00Z\n\nWrite a haiku about rain" in t
    assert "Soft rain on the roof,\nthe city hums low." in t and "Grey rain, empty street." in t
    assert "Gemini secrets" not in t


def test_gemini_html_and_json_side_by_side_reads_json_only(tmp_path):
    src = _zip(tmp_path / "t.zip", {"Takeout/My Activity/Gemini Apps/MyActivity.json": gemini_activity(),
                                    "Takeout/My Activity/Gemini Apps/MyActivity.html": GEMINI_HTML})
    convs, docs = _prep(tmp_path, src)
    assert len(convs) == 3 and not any("haiku" in t for t in docs.values())


# ── DeepSeek, Grok, Copilot, Le Chat ─────────────────────────────────────

def test_deepseek_main_branch_without_thinking(tmp_path):
    src = _zip(tmp_path / "deepseek_data.zip", {"conversations.json": deepseek_export(), "user.json": {"id": "x"}})
    convs, docs = _prep(tmp_path, src)
    assert [r["source"] for r in convs] == ["deepseek"]
    t = docs["ds-0001-aaaa"]
    assert "## Assistant (DeepSeek), 2025-02-10T00:00:09Z\n\nNo: 91 = 7 x 13." in t
    assert "OLD DEEPSEEK ANSWER" not in t and "SECRET REASONING" not in t
    assert convs[0]["file"].startswith("docs/deepseek_2025-02-10_primes_ds0001aa")


def test_grok_zip_newest_branch(tmp_path):
    src = _zip(tmp_path / "grok.zip", {"ttl/30d/export_data/u-1/prod-grok-backend.json": grok_export(),
                                       "ttl/30d/export_data/u-1/prod-mc-billing.json": {"credits": 1}})
    convs, docs = _prep(tmp_path, src)
    assert [r["source"] for r in convs] == ["grok"] and convs[0]["date"] == "2025-02-01"
    t = docs["grok-conv-0001"]
    assert "## Me, 2025-02-01T10:00:00Z\n\nRust or Go for a CLI?" in t
    assert "## Assistant (Grok), 2025-02-01T10:00:09Z\n\nGo, for the fast start." in t
    assert "OLD GROK ANSWER" not in t


def test_grok_bare_json(tmp_path):
    src = tmp_path / "prod-grok-backend.json"
    src.write_text(json.dumps(grok_export()))
    convs, _ = _prep(tmp_path, src)
    assert [r["source"] for r in convs] == ["grok"]


def test_copilot_csvs_grouped_by_name(tmp_path):
    src = tmp_path / "copilot-activity-history.csv"
    src.write_bytes(copilot_csv())
    convs, docs = _prep(tmp_path, src)
    assert sorted(r["title"] for r in convs) == ["Sourdough", "Trip to Lisbon"]
    t = next(t for t in docs.values() if "Lisbon" in t)
    assert t.startswith("# Trip to Lisbon\n")
    assert "## Me, 2025-05-01T09:00:00Z\n\nPlan three days in Lisbon" in t
    assert "## Assistant (Copilot), 2025-05-01T09:00:20Z\n\nDay 1" in t
    src2 = tmp_path / "copilot-chat-activity.csv"
    src2.write_bytes(copilot_chat_csv())
    convs2, docs2 = _prep(tmp_path / "b", src2)
    t2 = next(iter(docs2.values()))
    assert "## Me, 2025-05-06T08:00:00Z\n\nSummarise this memo" in t2 and "## Assistant (Copilot)" in t2


def test_lechat_json_in_unknown_named_zip(tmp_path):
    src = _zip(tmp_path / "mistral.zip", {"export/chats-le-chat.json": lechat_export()})
    convs, docs = _prep(tmp_path, src)
    assert [r["source"] for r in convs] == ["lechat"]
    t = docs["lc-77770000"]
    assert "## Assistant (Le Chat), 2025-06-01T12:00:03Z\n\nje vais, tu vas, il va" in t
    assert convs[0]["file"].startswith("docs/lechat_2025-06-01_french-verbs_lc777700")


def test_claude_with_role_free_messages_stays_claude():
    """Claude's own shape keeps its source; Le Chat is only the role-without-sender shape."""
    c = {"uuid": "u1", "name": "x", "chat_messages": [{"sender": "human", "text": "hi"}]}
    assert ic.normalize(c)["source"] == "claude"


def test_formats_table_names_every_source():
    assert set(ic.FORMATS) == {"chatgpt", "claude", "gemini", "deepseek", "grok", "copilot", "lechat",
                               "perplexity", "pasted", "codex", "claude-code"}
    assert all(isinstance(v["verified"], bool) and v["note"] for v in ic.FORMATS.values())


# ── the fallback ─────────────────────────────────────────────────────────

def test_pasted_with_markers_names_the_vendor(tmp_path):
    src = tmp_path / "chat.txt"
    src.write_text("You said:\nWhat is entropy?\nChatGPT said:\nA measure of disorder.\nMore lines.\n"
                   "You: thanks\nChatGPT: welcome\n", encoding="utf-8")
    convs, docs = _prep(tmp_path, src)
    r = convs[0]
    assert r["source"] == "chatgpt" and int(r["turns"]) == 4
    t = docs[r["id"]]
    assert "## Me\n\nWhat is entropy?" in t
    assert "## Assistant (Chatgpt)\n\nA measure of disorder.\nMore lines." in t


def test_pasted_generic_markers_and_bold():
    turns, vendor = ic.pasted_turns("**User:** hi there\n**Assistant:** hello\n")
    assert turns == [("user", "", "hi there"), ("assistant", "", "hello")] and vendor == ""
    c = ic.pasted_conversation("**User:** hi there\n**Assistant:** hello\n", today="2026-11-16")
    assert c["source"] == "pasted" and c["title"] == "hi there"
    assert "## Assistant (AI)\n\nhello" in ic.render(c)


def test_pasted_without_markers_is_one_me_block():
    c = ic.pasted_conversation("Notes from a Perplexity thread\n\nLine two.", title="My notes", today="2026-11-16")
    assert c["turns"] == [("user", "", "Notes from a Perplexity thread\n\nLine two.")]
    assert c["source"] == "perplexity" and c["title"] == "My notes"


def test_pasted_html_page_lechat(tmp_path):
    src = tmp_path / "page.html"
    src.write_text("<html><head><title>Le Chat - Mistral AI</title><script>x=1</script></head><body>"
                   "<p>Me: bonjour</p><p>Le Chat: salut</p></body></html>", encoding="utf-8")
    convs, docs = _prep(tmp_path, src)
    assert convs[0]["source"] == "lechat" and convs[0]["title"] == "Le Chat - Mistral AI"
    t = docs[convs[0]["id"]]
    assert "## Me\n\nbonjour" in t and "## Assistant (Le Chat)\n\nsalut" in t and "x=1" not in t
    assert convs[0]["file"].startswith("docs/lechat_")


def _tiny_pdf(text):
    """A one-page pdf with one line of text, xref offsets computed."""
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
            b"/Resources << /Font << /F1 5 0 R >> >> >>",
            b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out, offs = bytearray(b"%PDF-1.4\n"), []
    for i, o in enumerate(objs, 1):
        offs.append(len(out))
        out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offs)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    return bytes(out)


def test_pasted_pdf(tmp_path):
    pytest.importorskip("pypdf")
    src = tmp_path / "thread.pdf"
    src.write_bytes(_tiny_pdf("User: what is 2+2 Assistant: four"))
    convs, docs = _prep(tmp_path, src, title="Arithmetic")
    assert len(convs) == 1 and convs[0]["title"] == "Arithmetic"
    assert "what is 2+2" in docs[convs[0]["id"]]


def test_binary_is_refused():
    with pytest.raises(ValueError):
        ic.file_text("x.bin", b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\xff")
