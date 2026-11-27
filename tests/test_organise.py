"""Your map (ORGANISE-1, 2026-11-26): api/organise.py, its routes, the bridge's first turn after a move-in,
and ui/lib/mapCard.js under node. A made-up student only (tests/fixtures/organise_student.py: 300 notes, 40
chats, German, English and Russian); no database, no model, no member data, no live brain."""
import collections
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests" / "fixtures"))

os.environ.setdefault("BRAIN_IDENTITY_SECRET", "test-only-secret")
_RUNTIME = tempfile.mkdtemp(prefix="organise-1-test-")
os.environ.setdefault("BRAIN_RUNTIME_DIR", _RUNTIME)
os.environ.setdefault("SETTINGS_PATH", os.path.join(_RUNTIME, "settings.json"))

np = pytest.importorskip("numpy")
from api import organise as o  # noqa: E402
import organise_student as st  # noqa: E402


class MemStore:
    """document_embeddings as the map sees it, in memory: name -> item, name -> area label."""

    def __init__(self, items, labels=None):
        self.docs = {i["name"]: dict(i) for i in items}
        self.lab = dict(labels or {})
        self.writes = 0

    def items(self, chats=None, only_unlabelled=False, limit=20000, names=None):
        out = []
        for n, it in sorted(self.docs.items()):
            if names and n not in names:
                continue
            if only_unlabelled and self.lab.get(n) is not None:
                continue
            out.append(dict(it))
        return out[:limit]

    def labels(self, names):
        return {n: self.lab.get(n) for n in names}

    def set_labels(self, by_area):
        self.writes += 1
        for area, names in by_area.items():
            for n in names:
                if area is None:
                    self.lab.pop(n, None)
                else:
                    self.lab[n] = area
        return sum(len(v) for v in by_area.values())

    def counts(self):
        c = collections.Counter(self.lab.get(n) or "" for n in self.docs)
        return dict(c)


def _purity(prop, truth):
    hit = 0
    for a in prop["areas"]:
        hit += collections.Counter(truth[n] for n in a["items"]).most_common(1)[0][1]
    return hit / sum(a["count"] for a in prop["areas"])


@pytest.fixture(scope="module")
def student():
    return st.student()


@pytest.fixture(scope="module")
def built(student):
    items, truth = student
    calls = []
    prop = o.build(items, lang="de", namer=lambda p: calls.append(p) or None)
    return prop, truth, calls


# ── the proposal ───────────────────────────────────────────────────────

def test_student_has_what_the_brief_asked(student):
    items, _ = student
    kinds = collections.Counter(i["kind"] for i in items)
    assert kinds == {"doc": 300, "chat": 40}
    text = " ".join(i["title"] for i in items)
    assert "Zellbiologie" in text and "Дневник" in text and "Explain cell membrane" in text   # de, ru, en


def test_four_to_nine_areas_each_with_count_examples_line(built):
    prop, truth, calls = built
    assert prop["state"] == "proposed"
    assert o.MIN_AREAS <= len(prop["areas"]) <= o.MAX_AREAS
    assert sum(a["count"] for a in prop["areas"]) == prop["total"] == 340
    for a in prop["areas"]:
        assert a["count"] == len(a["items"]) == a["docs"] + a["chats"]
        assert 1 <= len(a["examples"]) <= 3 and len({e["title"] for e in a["examples"]}) == len(a["examples"])
        assert a["line"] and a["name"]
    assert prop["id"].startswith("map_")


def test_one_area_per_subject_and_chats_meet_their_notes(built):
    prop, truth, _ = built
    assert _purity(prop, truth) >= 0.95
    for subject in ("bio", "hist", "math", "econ", "personal", "work"):
        # the chats and the laptop notes of one subject land in the same area
        homes = collections.Counter(a["id"] for a in prop["areas"] for n in a["items"] if truth[n] == subject)
        main, k = homes.most_common(1)[0]
        assert k >= 0.9 * sum(homes.values()), subject
        area = next(a for a in prop["areas"] if a["id"] == main)
        assert area["chats"] > 0 and area["docs"] > 0, subject


def test_old_things_are_the_archive(built):
    prop, truth, _ = built
    arch = [a for a in prop["areas"] if a.get("archive")]
    assert len(arch) == 1 and arch[0]["name"] == "Archiv"
    assert {truth[n] for n in arch[0]["items"]} == {"school"}
    assert prop["areas"][-1]["archive"]        # last on the card


def test_without_a_model_the_persons_own_folder_names_stand(built):
    prop, _, _ = built
    names = {a["name"] for a in prop["areas"]}
    assert {"Biologie", "Geschichte", "Mathe", "VWL", "Личное", "Werkstudent"} <= names
    assert prop["model_named"] is False


def test_one_model_call_for_the_whole_map_and_no_private_title(built, student):
    prop, _, calls = built
    items, _ = student
    assert len(calls) == 1                     # never one call per document
    private = [i["title"] for i in items if i["private"]]
    assert private
    shown = calls[0]
    leaked = [t for t in private if f"| {t} |" in shown or shown.endswith(f"| {t}") or f"Titles: {t} |" in shown]
    assert not leaked


def test_the_namer_names_in_the_persons_words(student):
    items, truth = student

    def namer(prompt):
        ids = [ln.split()[1] for ln in prompt.splitlines() if ln.startswith("Area ")]
        return "Sure:\n" + json.dumps([{"id": i, "name": f"Fach {k}", "line": "Alles zu diesem Fach."} for k, i in enumerate(ids)])
    prop = o.build(items, lang="de", namer=namer)
    assert prop["model_named"] is True
    assert sum(1 for a in prop["areas"] if a["name"].startswith("Fach ")) == len(prop["areas"]) - 1


def test_a_failing_or_wild_namer_changes_nothing(student):
    items, _ = student
    a = o.build(items, lang="de", namer=lambda p: (_ for _ in ()).throw(RuntimeError("down")))
    b = o.build(items, lang="de", namer=lambda p: '[{"id": "a99", "name": "x"}, {"id": "a1", "name": "<b>**Hi**</b>"}]')
    assert a["model_named"] is False
    hi = [x for x in b["areas"] if x["id"] == "a1"][0]["name"]
    assert hi == "Hi"


def test_same_holdings_same_map(student):
    items, _ = student
    assert o.build(items, lang="de")["id"] == o.build(list(reversed(items)), lang="de")["id"]


def test_without_embeddings_folders_and_words_still_make_a_map():
    # No stored vectors: the laptop files still sort by their folders and words. English chats share no
    # words with German notes, so only the embedding brings them together (measured: 0.82 overall).
    items, truth = st.student(with_vec=False)
    prop = o.build(items, lang="en")
    assert o.MIN_AREAS <= len(prop["areas"]) <= o.MAX_AREAS
    docs = {"areas": [{**a, "items": [n for n in a["items"] if not n.startswith("chatgpt_")]} for a in prop["areas"]]}
    docs["areas"] = [dict(a, count=len(a["items"])) for a in docs["areas"] if a["items"]]
    assert _purity(docs, truth) >= 0.95


def test_too_few_documents_no_map():
    items, _ = st.student()
    assert o.build(items[:5])["state"] == "too_few"


# ── edits before the yes ───────────────────────────────────────────────

def _fresh(built):
    return json.loads(json.dumps(built[0]))


def test_rename_merge_move_change_the_id(built):
    prop = _fresh(built)
    ids = [a["id"] for a in prop["areas"] if not a.get("archive")]
    i0 = prop["id"]
    o.edit(prop, {"op": "rename", "area": ids[0], "name": "  Bio   und Zellen "})
    assert prop["areas"][[a["id"] for a in prop["areas"]].index(ids[0])]["name"] == "Bio und Zellen"
    assert prop["id"] != i0
    a1 = next(a for a in prop["areas"] if a["id"] == ids[1])
    item = a1["items"][0]
    o.edit(prop, {"op": "move", "item": item, "to": ids[2]})
    a2 = next(a for a in prop["areas"] if a["id"] == ids[2])
    assert item in a2["items"] and item not in a1["items"] and a2["count"] == len(a2["items"])
    n = len(prop["areas"])
    total = sum(a["count"] for a in prop["areas"])
    o.edit(prop, {"op": "merge", "area": ids[3], "into": ids[2]})
    assert len(prop["areas"]) == n - 1 and sum(a["count"] for a in prop["areas"]) == total
    for bad in ({"op": "rename", "area": ids[0], "name": ""}, {"op": "merge", "area": ids[2], "into": ids[2]},
                {"op": "move", "item": "nope", "to": ids[0]}, {"op": "delete"},
                {"op": "rename", "area": ids[1], "name": "bio und zellen"}):
        with pytest.raises(o.EditError):
            o.edit(prop, bad)


# ── the yes, the world, undo, arrivals ─────────────────────────────────

def test_accept_labels_every_document_and_undo_restores(built, student, tmp_path):
    items, truth = student
    prop = _fresh(built)
    maps = o.Maps(tmp_path / "organise")
    before = {items[0]["name"]: "old-label"}
    store = MemStore(items, before)
    maps.write("proposal.json", prop)
    assert store.writes == 0                         # nothing labelled before the yes
    with pytest.raises(o.EditError):
        o.accept(maps, store, "map_stale")
    acc = o.accept(maps, store, prop["id"])
    assert acc["state"] == "accepted"
    assert all(store.lab.get(i["name"]) for i in items)
    bio = next(a for a in acc["areas"] if a["name"] == "Biologie")
    assert all(store.lab[n] == "Biologie" for n in bio["items"])
    assert maps.state()["state"] == "accepted"
    u = o.undo(maps, store)
    assert u["documents"] == 340
    assert store.lab == before                        # the labels as they were, the old one too
    back = maps.state()
    assert back["state"] == "proposed" and back["id"] == prop["id"]   # the map waits again
    with pytest.raises(o.EditError):
        o.undo(maps, store)


def test_world_is_written_and_undo_takes_back_only_its_own(built, student, tmp_path):
    items, _ = student
    prop = _fresh(built)
    maps = o.Maps(tmp_path / "organise")
    store = MemStore(items)
    root = tmp_path / "mira.world"
    root.mkdir()
    (root / "README.md").write_text("mine")           # a file the person made: never overwritten
    world = o.World(root, "mira", "https://mira.example", today="2026-11-26")
    maps.write("proposal.json", prop)
    acc = o.accept(maps, store, prop["id"], world=world)
    assert acc["world"] == "mira.world"
    assert (root / "README.md").read_text() == "mine"
    bio = (root / "biologie" / "index.md").read_text()
    assert bio.startswith("# Biologie\n\nCreated: 2026-11-26.")
    assert "## Documents" in bio and "## Chats" in bio
    assert "https://mira.example/upload?doc=laptop/Documents/Uni/Biologie/" in bio
    assert "https://mira.example/?continue=chatgpt_" in bio
    assert (root / "личное" / "index.md").exists()
    (root / "mathe" / "index.md").write_text("edited by mira")   # edited after: kept on undo
    u = o.undo(maps, store, world=world)
    assert not (root / "biologie").exists()
    assert (root / "mathe" / "index.md").read_text() == "edited by mira"
    assert (root / "README.md").read_text() == "mine"
    assert u["world_files_removed"] >= 5


def test_world_only_where_the_member_has_hands():
    assert o.world_from_env({}) is None
    w = o.world_from_env({"ORGANISE_WORLD_HOST_DIR": "/home/anne-hands/anne.world", "CONSOLE_PUBLIC_URL": "https://anne.example"})
    assert str(w.root) == "/app/world" and w.owner == "anne" and w.url == "https://anne.example"


def test_new_files_go_to_their_area_or_unsorted(built, student, tmp_path):
    items, _ = student
    prop = _fresh(built)
    maps = o.Maps(tmp_path / "organise")
    store = MemStore(items)
    maps.write("proposal.json", prop)
    o.accept(maps, store, prop["id"])
    acc = maps.read("accepted.json")
    rng = __import__("random").Random(1)
    centre = [sum(i["vec"][d] for i in items if "Biologie" in i["name"]) / 60 for d in range(64)]
    new_bio = {"name": "laptop/Documents/Uni/Biologie/Neue_Vorlesung_Zellteilung.md", "kind": "doc", "title": "Zellteilung Vorlesung",
               "summary": "Mitose Chromosom Zelle", "vec": [c + rng.gauss(0, 0.35) for c in centre]}
    assert o.assign(acc, new_bio) == "Biologie"
    stray = {"name": "laptop/Downloads/qzx.bin", "kind": "doc", "title": "qzxv", "summary": "",
             "vec": [rng.gauss(0, 1) for _ in range(64)]}
    assert o.assign(acc, stray) == o.UNSORTED
    store.docs[new_bio["name"]] = new_bio
    store.docs[stray["name"]] = stray
    got = o.sort_arrivals(maps, store)
    assert got == {"Biologie": 1, "unsorted": 1}
    assert store.lab[stray["name"]] == "unsorted"
    assert o.sort_arrivals(maps, store) == {}          # labelled once
    o.undo(maps, store)
    assert new_bio["name"] not in store.lab and stray["name"] not in store.lab


def test_no_map_no_arrival_sorting(student, tmp_path):
    items, _ = student
    store = MemStore(items)
    assert o.sort_arrivals(o.Maps(tmp_path / "x"), store) == {} and store.writes == 0


def test_public_view_carries_no_feature_space(built):
    pub = o.public(built[0])
    assert "_space" not in pub and "titles" not in pub
    assert all(a["items"] == [] for a in pub["areas"])
    assert len(json.dumps(pub)) < 20000


# ── the routes ─────────────────────────────────────────────────────────

@pytest.fixture
def api(monkeypatch, tmp_path, student):
    from api import main as m
    from fastapi.testclient import TestClient
    items, _ = student
    store = MemStore(items)
    monkeypatch.setattr(m, "ORGANISE", o.Maps(tmp_path / "organise"))
    monkeypatch.setattr(m, "_ORG_STORE", store)
    monkeypatch.setattr(m, "_org_docs", lambda: len(store.docs))
    monkeypatch.setattr(m, "_org_chats", lambda: {})
    calls = []

    async def fake_complete(model, messages, max_tokens=0):
        calls.append(messages[0]["content"])
        return "not json"
    monkeypatch.setattr(m._providers, "complete", fake_complete)
    monkeypatch.setattr(m._providers, "default_model", lambda: "test-model")
    monkeypatch.delenv("ORGANISE_WORLD_HOST_DIR", raising=False)
    monkeypatch.delenv("ORGANISE_WORLD_DIR", raising=False)
    return types.SimpleNamespace(c=TestClient(m.app), m=m, store=store, calls=calls)


def test_routes_propose_edit_accept_undo(api):
    c = api.c
    s0 = c.get("/organise").json()
    assert s0["state"] == "none" and s0["ready"] is True
    p = c.post("/organise/propose", json={"lang": "de"}).json()
    assert p["state"] == "proposed" and len(api.calls) == 1 and api.store.writes == 0
    assert "_space" not in p
    a0 = p["areas"][0]["id"]
    items = c.get(f"/organise/area?id={a0}").json()["items"]
    assert len(items) == p["areas"][0]["count"] and {"name", "title", "kind"} <= set(items[0])
    p2 = c.post("/organise/edit", json={"op": "rename", "area": a0, "name": "Meins"}).json()
    assert p2["id"] != p["id"]
    assert c.post("/organise/edit", json={"op": "merge", "area": a0, "into": a0}).status_code == 400
    assert c.post("/organise/accept", json={"id": p["id"]}).status_code == 409     # the old id: the map changed
    acc = c.post("/organise/accept", json={"id": p2["id"]}).json()
    assert acc["state"] == "accepted"
    assert sum(1 for v in api.store.lab.values() if v == "Meins") == p["areas"][0]["count"]
    s1 = c.get("/organise").json()
    assert s1["state"] == "accepted" and s1["undo"] is True and s1["labels"]["Meins"] == p["areas"][0]["count"]
    assert c.post("/organise/edit", json={"op": "rename", "area": a0, "name": "x"}).status_code == 409
    u = c.post("/organise/undo").json()
    assert u["documents"] == 340 and not api.store.lab
    assert c.get("/organise").json()["state"] == "proposed"


def test_route_arrival_hook_sorts_one_new_document(api):
    c = api.c
    p = c.post("/organise/propose", json={"lang": "de"}).json()
    c.post("/organise/accept", json={"id": p["id"]})
    api.store.docs["laptop/Documents/Uni/Mathe/Neu_Eigenwerte.md"] = {
        "name": "laptop/Documents/Uni/Mathe/Neu_Eigenwerte.md", "kind": "doc", "title": "Eigenwerte Matrix Beweis", "summary": "Matrix Vektor Eigenwert", "vec": None}
    api.m._organise_arrival("laptop/Documents/Uni/Mathe/Neu_Eigenwerte.md")
    assert api.store.lab["laptop/Documents/Uni/Mathe/Neu_Eigenwerte.md"] == "Mathe"


def test_not_ready_while_the_first_pass_reads(api, monkeypatch):
    monkeypatch.setitem(api.m._APPROVE_ALL, "running", True)
    monkeypatch.setitem(api.m._APPROVE_ALL, "first_total", 50)
    monkeypatch.setitem(api.m._APPROVE_ALL, "first_done", 10)
    assert api.c.get("/organise").json()["ready"] is False
    monkeypatch.setitem(api.m._APPROVE_ALL, "first_done", 50)
    assert api.c.get("/organise").json()["ready"] is True


# ── the bridge's first turn: the map, then the one question ────────────

def _bridge(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("CC_CWD", str(tmp_path / "brain"))
    monkeypatch.setenv("BRAIN_API_KEY", "test-key")
    spec = importlib.util.spec_from_file_location("cc_bridge_org", ROOT / "scripts" / "cc" / "cc-bridge.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["cc_bridge_org"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_first_turn_opens_with_the_map_once(monkeypatch, tmp_path, built):
    m = _bridge(monkeypatch, tmp_path)
    m.PERSONA_FILE = tmp_path / "persona.md"
    m.PERSONA_FILE.write_text("# Name\nplain persona\n")
    m.MAP_INTRO_FILE = tmp_path / "map-intro.json"
    pub = o.public(built[0])
    monkeypatch.setattr(m, "_owner_documents", lambda: 340)
    monkeypatch.setattr(m, "_owner_map", lambda: pub)
    fu = m._first_use(True)
    assert "After a move-in: the map first" in fu and "this is what I found of yours" in fu
    assert "- Biologie (" in fu and "- Archiv (" in fu
    assert m._first_use(True) == ""                    # once per map
    monkeypatch.setattr(m, "_owner_map", lambda: {**pub, "id": "map_other"})
    assert m._first_use(True) != ""                    # a new map is told again
    monkeypatch.setattr(m, "_owner_map", lambda: None)
    assert m._first_use(True) == ""                    # documents, no map: as before
    monkeypatch.setattr(m, "_owner_documents", lambda: 0)
    assert "docs/first-use.md" in m._first_use(True)   # empty brain: one question, one document, as before


def test_docs_say_the_map_comes_before_the_intro():
    fu = (ROOT / "docs" / "first-use.md").read_text()
    assert "## After a move-in: the map first (ORGANISE-1, 2026-11-26)" in fu
    assert fu.index("the map first") < fu.index("## The first turn")
    ready = (ROOT / "docs" / "MEMBER_READY.md").read_text()
    assert "| 14 | their map |" in ready and "recognises their own areas" in ready


def test_member_gets_a_world_folder():
    sys.path.insert(0, str(ROOT / "scripts"))
    import member_env
    assert member_env.member_values("anne", 3)["ORGANISE_WORLD_HOST_DIR"] == "/home/anne-hands/anne.world"
    assert 'install -d -o "$HANDS_USER" -g "$HANDS_USER" -m 755 "/home/$HANDS_USER/$HANDLE.world"' in (ROOT / "scripts" / "add-member.sh").read_text()
    assert "${ORGANISE_WORLD_HOST_DIR:-organise_world}:/app/world" in (ROOT / "docker-compose.yml").read_text()


# ── the card's rules under node ────────────────────────────────────────

def _node(script):
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")
    r = subprocess.run([node, "-e", "const m=require('./mapCard.js');" + script], capture_output=True, text=True,
                       timeout=30, cwd=str(ROOT / "ui" / "lib"))
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_card_rules():
    out = _node("""const A=[{id:'archive',name:'Archiv',count:30,archive:true},{id:'a1',name:'Bio',count:9},{id:'a2',name:'Mathe',count:40}];
      console.log(JSON.stringify([m.mapStep(null), m.mapStep({state:'none',ready:false}), m.mapStep({state:'none',ready:true}),
        m.mapStep({state:'proposed',areas:A}), m.mapStep({state:'accepted',areas:A}), m.mapStep({state:'too_few'}),
        m.chips({areas:A}).map(c=>c.id), m.renameOp('a1','  New   name '), m.renameOp('a1','   '), m.mergeOp('a1','a1'),
        m.mergeOp('a1','a2'), m.moveOp('x','a2'), m.arrivedSince({areas:A,labels:{'':3,Bio:10,Mathe:40,Archiv:30,unsorted:2}})]))""")
    assert out[:6] == ["hidden", "hidden", "propose", "proposed", "accepted", "hidden"]
    assert out[6] == ["a2", "a1", "archive"]
    assert out[7] == {"op": "rename", "area": "a1", "name": "New name"} and out[8] is None and out[9] is None
    assert out[10] == {"op": "merge", "area": "a1", "into": "a2"} and out[11] == {"op": "move", "item": "x", "to": "a2"}
    assert out[12] == 3


def test_card_words_every_language_every_key():
    out = _node("""const k=l=>Object.keys(m.MAP_TEXT[l]).sort(); console.log(JSON.stringify([k('en'),k('ru'),k('de'),
      m.mapWords('ru').found(21,3,5), m.mapWords('en').found(1,0,4), m.mapWords('xx').title]))""")
    assert out[0] == out[1] == out[2]
    assert out[3] == "Вот что я нашёл вашего: 21 документ и 3 чата, 5 областей."
    assert out[4] == "This is what I found of yours: 1 document, in 4 areas."
    assert out[5] == "Your map"


def test_pg_store_falls_back_when_avg_is_missing():
    class Cur:
        def __init__(self, db): self.db = db; self.rowcount = 0
        def execute(self, sql, args=()):
            self.db.sql.append(sql)
            if "AVG(embedding)" in sql:
                raise RuntimeError("function avg(vector) does not exist")
        def fetchall(self):
            return [("laptop/Documents/Uni/Mathe/a.md", None, "Matrix", False, "[0.1,0.2]"),
                    ("chatgpt_x-1.md", "x", "", True, None)]
        def close(self): pass

    class Conn:
        def __init__(self, db): self.db = db
        def cursor(self): return Cur(self.db)
        def rollback(self): self.db.rolled += 1
        def close(self): pass
    db = types.SimpleNamespace(sql=[], rolled=0)
    items = o.PgStore(lambda: Conn(db)).items()
    assert db.rolled == 1 and len(db.sql) == 2
    assert items[0]["vec"] == [0.1, 0.2] and items[0]["kind"] == "doc"
    assert items[1]["kind"] == "chat" and items[1]["private"] is True and items[1]["vec"] is None
