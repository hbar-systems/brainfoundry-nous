"""Tests for scripts/sort_inbox.py: the inbox sorter, its manifest through the
import_chats.py gate, and the persona draft. Every file is made up here.

Created 2026-10-17.
"""
import importlib.util
import json
import pathlib
import tempfile
import unittest
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("sort_inbox", ROOT / "scripts" / "sort_inbox.py")
si = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(si)
ic = si.ic


class FakeBrain:
    def __init__(self):
        self.permits, self.proposals, self.approved = [], {}, []

    def permit(self):
        self.permits.append(f"permit-{len(self.permits)}")
        return self.permits[-1]

    def propose(self, permit_id, name, data, layer=None):
        pid = f"prop-{len(self.proposals)}"
        self.proposals[pid] = (permit_id, name, data)
        return {"status": "PENDING", "proposal_id": pid, "injection_scan": {"risk": "none"}}

    def approve(self, ids):
        self.approved.extend(ids)
        return {"running": False, "total": len(ids), "done": len(ids), "failed": []}


def _docx(path, paragraphs):
    body = "".join(f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>" for p in paragraphs)
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("word/document.xml", f'<w:document xmlns:w="x"><w:body>{body}</w:body></w:document>')


def make_inbox(root):
    inbox = root / "inbox"
    (inbox / "old laptop" / "chatgpt-export").mkdir(parents=True)
    (inbox / "misc").mkdir()
    w = lambda rel, text: (inbox / rel).write_text(text, encoding="utf-8")
    w("about-me.md", "# About me\n\nName: Ada Example\nI grow tomatoes and build small boats.\nI live by the sea.\n")
    w("boat-project-roadmap.md", "# Boat roadmap\n\n## Milestones\n- hull\n- sail\n")
    w("essay_on_tides.md", "# On tides\n\nI have watched the water for years. The moon pulls it. I keep notes.\n")
    w("2024-03-09.txt", "rained, fixed the mast\n")
    w("misc/untitled.md", "lorem ipsum dolor sit amet, a long line of nothing in particular here\n")
    w("misc/copy of essay.md", (inbox / "essay_on_tides.md").read_text())  # exact duplicate
    w("bank-statement-2024.txt", "account 0000\n")
    w("misc/ideas.txt", "- a\n- b\n- c\n")
    (inbox / "photo.jpg").write_bytes(b"\xff\xd8\xff fake jpeg")
    (inbox / "voice memo.m4a").write_bytes(b"fake audio")
    (inbox / ".DS_Store").write_bytes(b"x")
    _docx(inbox / "chapter one.docx", ["Chapter one", "It was a calm morning."])
    conv = [{"uuid": "c1", "name": "Sails", "created_at": "2024-05-01T10:00:00Z",
             "chat_messages": [{"sender": "human", "text": "Which sail?"},
                               {"sender": "assistant", "text": "A jib."}]}]
    (inbox / "old laptop" / "chatgpt-export" / "conversations.json").write_text(json.dumps(conv))
    (inbox / "old laptop" / "chatgpt-export" / "users.json").write_text("[]")
    with zipfile.ZipFile(inbox / "claude-data.zip", "w") as z:
        z.writestr("conversations.json", json.dumps([dict(conv[0], uuid="c2", name="Knots")]))
    return inbox


class SortTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        self.inbox = make_inbox(self.root)
        self.out = self.root / "sorted"
        self.logs = []
        self.rows = si.sort_inbox(self.inbox, self.out, log=self.logs.append)
        self.by = {r["source"]: r for r in self.rows}

    def tearDown(self):
        self.tmp.cleanup()

    def test_rules_place_every_file_with_a_reason(self):
        b = self.by
        self.assertEqual(b["about-me.md"]["area"], "identity")
        self.assertEqual(b["boat-project-roadmap.md"]["area"], "projects")
        self.assertEqual(b["essay_on_tides.md"]["area"], "writing")
        self.assertEqual(b["chapter one.docx"]["area"], "writing")
        self.assertEqual(b["2024-03-09.txt"]["area"], "thinking")
        self.assertEqual(b["misc/ideas.txt"]["area"], "thinking")
        self.assertEqual(b["misc/untitled.md"]["area"], "library")
        self.assertEqual(b["photo.jpg"]["area"], "library")
        self.assertEqual(b["voice memo.m4a"]["area"], "library")
        self.assertEqual(b["bank-statement-2024.txt"]["area"], "outside")
        self.assertNotIn(".DS_Store", b)
        self.assertTrue(all(r["reason"] for r in self.rows))

    def test_duplicates_and_outside_are_not_copied(self):
        self.assertEqual(self.by["misc/copy of essay.md"]["area"], "duplicate")
        self.assertIn("essay_on_tides.md", self.by["misc/copy of essay.md"]["reason"])
        self.assertFalse(list(self.out.rglob("bank-statement*")))
        self.assertTrue((self.out / "identity" / "about-me.md").exists())
        self.assertTrue((self.inbox / "about-me.md").exists())  # the inbox is never changed

    def test_exports_go_to_import_chats_prep(self):
        exp = [r for r in self.rows if r["area"] == "chat-export"]
        self.assertEqual(len(exp), 2)
        for r in exp:
            self.assertTrue((self.out / r["file"] / "index.tsv").exists())
        self.assertNotIn("old laptop/chatgpt-export/users.json", self.by)

    def test_manifest_and_summary(self):
        rows = ic.read_tsv(self.out / "manifest.tsv")
        self.assertEqual({r["area"] for r in rows}, set(si.MEMORY_AREAS))
        self.assertTrue(all(r["name"].split("/")[0] == r["area"] for r in rows))
        self.assertEqual(len(rows), 6)
        head = (self.out / "manifest.tsv").read_text().splitlines()[0]
        self.assertEqual(head, f"# manifest_id: {ic.manifest_id(rows)}")
        s = self.logs[0]
        self.assertTrue(s.startswith("11 files: 1 identity, 1 projects, 2 writing, 2 thinking, 3 library, 1 outside"), s)
        self.assertIn("; 1 duplicate skipped; 2 chat exports", s)
        self.assertIn(ic.manifest_id(rows), s)

    def test_propose_and_approve_through_the_existing_gate(self):
        brain = FakeBrain()
        ic.propose_manifest(self.out, brain, log=lambda *_: None)
        names = sorted(n for _, n, _ in brain.proposals.values())
        self.assertIn("identity/about-me.md", names)
        self.assertIn("writing/chapter one.docx", names)
        self.assertFalse(brain.approved)  # nothing remembered before the yes
        with self.assertRaises(SystemExit):
            ic.approve_manifest(self.out, brain, "0" * 16, log=lambda *_: None)
        mid = ic.manifest_id(ic.read_tsv(self.out / "manifest.tsv"))
        rec = ic.approve_manifest(self.out, brain, mid, log=lambda *_: None)
        self.assertEqual(rec["proposals"], 6)

    def test_owner_moves_a_row_then_a_new_manifest(self):
        old = ic.manifest_id(ic.read_tsv(self.out / "manifest.tsv"))
        p = self.out / "sorted.tsv"
        p.write_text(p.read_text().replace("misc/untitled.md\t" + self.by["misc/untitled.md"]["sha256"] + "\tlibrary",
                                           "misc/untitled.md\t" + self.by["misc/untitled.md"]["sha256"] + "\tthinking"))
        p.write_text(p.read_text().replace("\twriting\tname has 'essay'", "\toutside\tname has 'essay'"))
        new = si.remanifest(self.out, log=lambda *_: None)
        self.assertNotEqual(old, new)
        self.assertTrue((self.out / "thinking" / "untitled.md").exists())
        self.assertFalse((self.out / "writing" / "essay_on_tides.md").exists())
        rows = ic.read_tsv(self.out / "manifest.tsv")
        self.assertIn("thinking/untitled.md", [r["name"] for r in rows])
        self.assertNotIn("writing/essay_on_tides.md", [r["name"] for r in rows])

    def test_persona_draft_and_approve(self):
        did = si.persona_draft(self.out)
        text = (self.out / "persona_draft.md").read_text()
        self.assertTrue(text.startswith("# DRAFT"))
        self.assertIn("personal brain of Ada Example", text)
        self.assertIn("I grow tomatoes and build small boats. (identity/about-me.md)", text)
        self.assertIn("Boat roadmap (projects/boat-project-roadmap.md)", text)
        self.assertIn("Governance:", text)  # the template's shape is kept
        self.assertNotIn("[CONFIGURE", text)
        put = []
        with self.assertRaises(SystemExit):
            si.persona_approve(self.out, "0" * 16, put.append, log=lambda *_: None)
        self.assertFalse(put)
        rec = si.persona_approve(self.out, did, put.append, log=lambda *_: None)
        self.assertFalse(put[0].startswith("#"))
        self.assertTrue(put[0].startswith("You are [BRAIN_NAME]"))
        self.assertEqual(rec["placeholders_left"], ["[BRAIN_NAME]"])
        # an edit after the id was shown changes the id: the old yes no longer fits
        (self.out / "persona_draft.md").write_text(text + "\nmore\n")
        with self.assertRaises(SystemExit):
            si.persona_approve(self.out, did, put.append, log=lambda *_: None)


class LlmTest(unittest.TestCase):
    def test_llm_only_for_unplaced_text_and_rules_stand_without_it(self):
        with tempfile.TemporaryDirectory() as t:
            inbox = make_inbox(pathlib.Path(t))
            asked = []

            def llm(name, text):
                asked.append(name)
                return ("thinking", "loose musing")
            rows = si.sort_inbox(inbox, pathlib.Path(t) / "o", llm=llm, log=lambda *_: None)
            by = {r["source"]: r for r in rows}
            self.assertEqual(asked, ["untitled.md"])
            self.assertEqual(by["misc/untitled.md"]["area"], "thinking")
            self.assertIn("the brain's model", by["misc/untitled.md"]["reason"])

            def broken(name, text):
                raise ConnectionError("down")
            rows = si.sort_inbox(inbox, pathlib.Path(t) / "o2", llm=broken, log=lambda *_: None)
            self.assertEqual({r["source"]: r for r in rows}["misc/untitled.md"]["area"], "library")

    def test_parse_llm_answer(self):
        ok = {"choices": [{"message": {"content": 'Sure: {"area": "Writing", "reason": "a poem"}'}}]}
        self.assertEqual(si.parse_llm_answer(ok), ("writing", "a poem"))
        self.assertIsNone(si.parse_llm_answer({"choices": [{"message": {"content": '{"area": "outside"}'}}]}))
        self.assertIsNone(si.parse_llm_answer({}))


class ContentTypeTest(unittest.TestCase):
    def test_types_and_names(self):
        self.assertEqual(ic.content_type("a/b.pdf"), "application/pdf")
        self.assertTrue(ic.content_type("x.DOCX").endswith("document"))
        self.assertEqual(ic.content_type("chatgpt_x.md"), "text/markdown")
        self.assertEqual(ic.doc_name({"file": "docs/a.md"}), "a.md")
        self.assertEqual(ic.doc_name({"file": "identity/a.md", "name": "identity/a.md"}), "identity/a.md")


if __name__ == "__main__":
    unittest.main()
