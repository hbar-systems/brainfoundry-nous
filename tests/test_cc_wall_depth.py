"""The wall's depth (WALL-3, 2026-11-24): everything about a system one press away; systems and surfaces told apart.

hbar: "will i be satisfied with the number of information i can get about the system (and talkign to it: ex: how many
jobs are going, maybe agentic substructure of each job or info, clear summary, this thing too (see image 3) and so i
can also maybe red the thread if i wanted too etc. but like everything is hidden, and i can gain access some easy way
WITHOUT interfering with production and the main focus." And: "dont confuse systems with surfaces".

Pins: cc_systems' pure parts (a registry row's kind, the card line, the answer's first line, the last tree, the
waiter, a job's steps and files, tasks due today); GET /cc/systems carrying kind, summary, jobs, tree_n and waits
from what the poll already holds (no second ask of the brain), the tree only on ?depth=<id>; and ui/lib/wall.js under
node (kindOf, openOf, depthOf, jobLines, jobsBySystem, addGroups, systemsUrl, an instrument never in the starting
orbit). Also the page's wiring: the layer only reads (no send, no navigation), an instrument has no box, the tree's
Talk fills the box. The browser half (open and close send nothing, stop nothing) is tests/browser/test_wall_depth.py.

Run from repo root:
    pytest tests/test_cc_wall_depth.py -v
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import time
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "scripts" / "cc"))
import cc_systems as C  # noqa: E402
import test_cc_steer as S  # noqa: E402
import test_cc_wall as WL  # noqa: E402

FILM = S.FILM
TREE = {"title": "This thread", "nodes": [{"id": "1", "label": "Cut the trailer", "state": "done"},
                                          {"id": "2", "label": "Colour pass", "state": "running",
                                           "children": [{"id": "2.1", "label": "Grade", "state": "yours"}]}]}


# ---- pure parts ----
def test_kind_from_the_registry_defaults_to_work(tmp_path):
    (tmp_path / "registry").mkdir()
    (tmp_path / "registry" / "systems.json").write_text(json.dumps({"systems": [
        {"id": "hbar.music", "description": "m"}, {"id": "hbar.ink", "kind": "instrument", "domains": ["hbar.ink"]},
        {"id": "hbar.blog", "kind": "site"}, {"id": "hbar.odd", "kind": "toy"}]}))
    got = {s["id"]: (s["kind"], s["domain"]) for s in C.load_systems(tmp_path)}
    assert got["hbar.music"] == ("work", "") and got["hbar.ink"] == ("instrument", "hbar.ink")
    assert got["hbar.blog"][0] == "site" and got["hbar.odd"][0] == "work" and got["world"][0] == "work"


def test_card_line_and_first_line():
    card = "---\ncreated: 2026-11-24\n---\n# MEDIA lane\n\nScope: the **Sunday video** first. Then the channels.\n"
    assert C.card_line(card) == "the Sunday video first."
    assert C.card_line("# X\n\nThe [studio](/studio) is warm today. More.") == "The studio is warm today."
    ans = "## Done\n```\ncode\n```\n| a | b |\n- I cut the trailer to 40 s. It is in out/film.\n"
    assert C.first_line(ans) == "I cut the trailer to 40 s."
    assert C.first_line("") == "" and len(C.first_line("word " * 200)) <= C.SUMMARY_MAX + 2


def test_last_tree_is_the_newest_that_parses():
    msgs = [{"role": "assistant", "content": "a <tree>" + json.dumps({"nodes": [{"label": "old"}]}) + "</tree>"},
            {"role": "user", "content": "<tree>{\"nodes\": [{\"label\": \"from the user\"}]}</tree>"},
            {"role": "assistant", "content": "b <tree>" + json.dumps(TREE) + "</tree> and <tree>{broken</tree>"},
            {"role": "assistant", "content": "the last answer has none"}]
    t = C.last_tree(msgs)
    assert t["title"] == "This thread" and C.tree_size(t) == 3
    assert C.last_tree([{"role": "assistant", "content": "<tree>[{\"label\": \"a list\"}]</tree>"}]) == {"nodes": [{"label": "a list"}]}
    assert C.last_tree([{"role": "assistant", "content": "no tree"}]) is None
    big = {"nodes": [{"label": "x" * 100}] * 1000}
    assert C.last_tree([{"role": "assistant", "content": "<tree>" + json.dumps(big) + "</tree>"}]) is None


def test_waiter_steps_and_tasks_due(tmp_path):
    world = tmp_path / "world"
    (world / "ops" / "jobs" / "briefs").mkdir(parents=True)
    (world / "ops" / "jobs" / "briefs" / "2026-11-24_push-train-9.md").write_text("Wait for SKIN-9 and FRONT-1, gate, push.")
    jobs = [{"id": "J1", "title": "SKIN-9 Skin: the colours", "command": "claude -p \"$(cat ops/jobs/briefs/2026-11-24_skin-9.md)\"", "ended": None, "started": 100},
            {"id": "J2", "title": "PUSH-TRAIN-9 Conductor", "command": "claude -p \"$(cat ops/jobs/briefs/2026-11-24_push-train-9.md)\"", "ended": None},
            {"id": "J3", "title": "SKIN-90 other", "command": "", "ended": None},
            {"id": "J4", "title": "SKIN-9-PUSH: waits for SKIN-9", "command": "", "ended": 5}]
    assert C.waiter_of(jobs[0], jobs, world) == {"id": "J2", "title": "PUSH-TRAIN-9 Conductor"}   # ended J4 is no waiter
    assert C.waiter_of(jobs[2], jobs, world) is None                                           # SKIN-9 is not SKIN-90
    now = datetime.fromtimestamp(100 + 25 * 60, timezone.utc)
    b = C.job_briefs([jobs[0]], jobs, now, world)[0]
    assert b["mins"] == 25 and b["brief"] == "2026-11-24_skin-9.md" and b["tag"] == "SKIN-9" and b["waiter"]["id"] == "J2"
    out = tmp_path / "out"
    started = time.time() - 60
    day = time.strftime("%Y-%m-%d", time.gmtime(started))
    (out / day / "skin-9").mkdir(parents=True)
    (out / day / "skin-9" / "REPORT.md").write_text("x")
    log = out / "J1.log"
    log.write_text("# J1 2026-11-24T10:00:00Z in /w\n# claude -p ...\nreading the page\n\nbuilding the console\n")
    st = C.job_steps(str(log), "", out, "2026-11-24_skin-9.md", started)
    assert st == {"steps": ["reading the page", "building the console"], "made": ["REPORT.md"]}
    assert C.job_steps("", "", out, "../etc", started) == {"steps": [], "made": []}
    tasks = [{"due": "2026-11-24T18:00:00Z"}, {"due": "2026-11-20"}, {"due": "2026-11-25"}, {"due": None}, {"due": "2026-11-24", "done": True}]
    assert C.due_today(tasks, "2026-11-24") == 2


def test_state_cards_stay_inside_the_world(tmp_path):
    (tmp_path / "ops" / "wall").mkdir(parents=True)
    (tmp_path / "ops" / "wall" / "states.json").write_text(json.dumps({"states": {
        "hbar.media": "ops/lanes/MEDIA.md", "hbar.x": "/etc/passwd", "hbar.y": "../out/z.md", "Bad Id": "a.md"}}))
    assert C.state_cards(tmp_path) == {"hbar.media": "ops/lanes/MEDIA.md"}


# ---- the bridge ----
def _depth_bridge(monkeypatch, tmp_path, messages, tasks=None, jobs=None):
    m = S._bridge(monkeypatch, tmp_path)
    asked = []

    def api(method, path, body=None):
        asked.append((method, path))
        if method == "GET" and path == f"/sessions/{FILM}/messages":
            return messages
        if method == "GET" and path == "/tasks":
            return {"tasks": tasks or []}
        return {}
    monkeypatch.setattr(m, "_brain_api", api)
    monkeypatch.setattr(m.JOBS, "list", lambda n=200: list(jobs or []))
    m._SYSTEMS_TASKS[0] = 0.0
    m._SYSTEMS_OPEN[0] = 0.0
    return m, asked


HIST = {"messages": [{"role": "assistant", "content": "I graded the first reel. The colour is warm.\n\n<tree>" + json.dumps(TREE) + "</tree>"}]}


def test_systems_tiles_carry_summary_jobs_tree_and_waits(monkeypatch, tmp_path):
    started = int(time.time()) - 12 * 60
    jobs = [{"id": "J9", "title": "FILM-2 Grade: hbar.film colour pass", "command": "echo", "started": started, "ended": None, "system": "hbar.film"}]
    today = time.strftime("%Y-%m-%d", time.gmtime())
    m, asked = _depth_bridge(monkeypatch, tmp_path, HIST, tasks=[{"due": today + "T20:00:00Z"}], jobs=jobs)
    d = m._systems_view()
    tl = {t["id"]: t for t in d["tiles"]}
    f = tl["hbar.film"]
    assert f["kind"] == "work" and f["summary"] == {"text": "I graded the first reel.", "from": "thread"}
    assert f["tree_n"] == 3 and "tree" not in f                                  # the tree itself only on ?depth=
    assert [j["id"] for j in f["jobs"]] == ["J9"] and f["jobs"][0]["mins"] in (11, 12, 13)
    assert "steps" in f["jobs"][0] and "made" in f["jobs"][0]
    assert d["waits"]["tasks_today"] == 1 and isinstance(d["waits"]["court"], int)
    d2 = m._systems_view("hbar.film")
    assert {t["id"]: t for t in d2["tiles"]}["hbar.film"]["tree"]["title"] == "This thread"
    # the same read as `said`: the brain is asked once for the thread, whatever the depth
    assert asked.count(("GET", f"/sessions/{FILM}/messages")) == 1
    assert asked.count(("GET", "/tasks")) == 1                                   # tasks cached between polls
    assert all(meth == "GET" for meth, _ in asked)                               # the layer's data only reads


def test_a_mapped_state_card_wins(monkeypatch, tmp_path):
    m, _ = _depth_bridge(monkeypatch, tmp_path, HIST)
    world = pathlib.Path(m.WORLD_DIR)
    (world / "ops" / "wall").mkdir(parents=True, exist_ok=True)
    (world / "ops" / "lanes").mkdir(parents=True, exist_ok=True)
    (world / "ops" / "lanes" / "FILM.md").write_text("# FILM lane\n\nState: K2 is released; the trailer is next.\n")
    (world / "ops" / "wall" / "states.json").write_text(json.dumps({"states": {"hbar.film": "ops/lanes/FILM.md"}}))
    f = {t["id"]: t for t in m._systems_view()["tiles"]}["hbar.film"]
    assert f["summary"] == {"text": "K2 is released; the trailer is next.", "from": "card"}


def test_depth_over_http_is_a_get(monkeypatch, tmp_path):
    m, asked = _depth_bridge(monkeypatch, tmp_path, HIST)
    srv, base = S._serve(m)
    try:
        st, d = S._call(base + "/systems?depth=hbar.film")
        assert st == 200
        tl = {t["id"]: t for t in d["tiles"]}
        assert tl["hbar.film"]["tree"]["nodes"][1]["children"][0]["label"] == "Grade"
        assert "tree" not in tl["hbar.music"] and tl["hbar.music"]["summary"] is None
        st, d = S._call(base + "/systems")
        assert all("tree" not in t for t in d["tiles"])
    finally:
        srv.shutdown()


# ---- ui/lib/wall.js under node ----
KTILES = r"""
const tile = (id, o) => Object.assign({ id, thread: null, said: null, counts: { running: 0 }, detail: {} }, o || {})
const TILES = [tile('world', { thread: 't-w' }), tile('hbar.music', { thread: 't-m', kind: 'work' }),
  tile('hbar.ink', { thread: 't-i', kind: 'instrument', open: '/apps/hbar-ink', counts: { running: 1 } }),
  tile('hbar.blog', { kind: 'site', domain: 'hbar.blog' }), tile('hbar.poker', { kind: 'instrument', domain: 'hbar.poker' }),
  tile('hbar.film', { counts: { running: 2 }, jobs: [{ id: 'J1', title: 'FILM-2 Grade: colour', mins: 75, brief: '2026-11-24_film-2.md',
    steps: ['reading the reel'], made: ['a.png', 'b.png'], waiter: { id: 'J2', title: 'PUSH-TRAIN-9 Conductor' } }, { id: 'J3', title: 'FILM-3', mins: 0 }],
    summary: { text: 'K2 is out.', from: 'card' }, tree_n: 3 })]
"""


def test_lib_kinds_open_and_depth():
    d = WL._node(WL.FAKE + KTILES + r"""
const by = Object.fromEntries(TILES.map(t => [t.id, t]))
console.log(JSON.stringify({
  kinds: TILES.map(W.kindOf), ink: W.openOf(by['hbar.ink']), poker: W.openOf(by['hbar.poker']), music: W.openOf(by['hbar.music']),
  evil: W.openOf({ open: '//evil.example/x', domain: 'javascript:alert(1)' }),
  start: W.keptSet(null, TILES, null),
  film: W.depthOf(by['hbar.film']), quiet: W.depthOf(by['hbar.music']),
  lines: W.jobLines(by['hbar.film'].jobs[0]), mins: [W.minsText(0), W.minsText(5), W.minsText(75), W.minsText(null)],
  groups: W.jobsBySystem(TILES).map(g => [g.id, g.jobs.length]),
  add: W.addGroups(TILES.filter(t => t.id !== 'world')).map(g => [g.kind, g.items.map(t => t.id)]),
  urls: [W.systemsUrl(null), W.systemsUrl('hbar.film')],
}))
""")
    assert d["kinds"] == ["work", "work", "instrument", "site", "instrument", "work"]
    assert d["ink"] == {"route": "/apps/hbar-ink"} and d["poker"] == {"href": "https://hbar.poker"} and d["music"] is None
    assert d["evil"] is None
    assert d["start"] == ["hbar.film", "hbar.music"]          # the instrument runs and has a thread, still not in the start
    f = d["film"]
    assert f["summary"] == {"text": "K2 is out.", "from": "card"} and f["jobs"]["n"] == 2
    assert f["jobs"]["line"] == "2 running: Grade: colour, 1 h 15" and f["tree"] == {"n": 3, "line": "3 branches"} and f["thread"] is False
    assert d["quiet"]["jobs"]["line"] == "nothing running" and d["quiet"]["tree"]["line"] == "no tree yet" and d["quiet"]["thread"] is True
    assert [x["k"] for x in d["lines"]] == ["brief", "step", "made", "pushed by"] and d["lines"][2]["text"] == "a.png, b.png"
    assert d["mins"] == ["just started", "5 min", "1 h 15", ""]
    assert d["groups"] == [["hbar.film", 2]]
    assert d["add"] == [["work", ["hbar.music", "hbar.film"]], ["instrument", ["hbar.ink", "hbar.poker"]], ["site", ["hbar.blog"]]]
    assert d["urls"] == ["/cc/systems", "/cc/systems?depth=hbar.film"]


# ---- the page ----
def test_page_wiring_the_layer_only_reads():
    w = (ROOT / "ui" / "pages" / "wall.js").read_text()
    o = (ROOT / "ui" / "components" / "WallOrbit.js").read_text()
    dp = (ROOT / "ui" / "components" / "WallDepth.js").read_text()
    tt = (ROOT / "ui" / "components" / "ThreadTree.js").read_text()
    assert "fetch(systemsUrl(depthRef.current)" in w and "if (depthRef.current) { depthRef.current = null; setDepthState(null); return }" in w
    assert "import WallDepth from './WallDepth'" in o and "data-depth-for={t.id}" in o and "data-depth-for={CENTRE}" in o
    assert "kindOf(t) !== 'work'" in o and "if (inst) { onOpen(t); return }" in o            # an instrument opens, it has no box
    assert "fill={fills[id]}" in o and "onDepth(null)" in o
    for bad in ("fetch(", "method:", "sendText", "sendClip", "router", "location.href", "<select"):
        assert bad not in dp, bad                                                   # the layer itself never sends or navigates
    assert "<ThreadTree tree={tree} cur={null} onTalk=" in dp
    assert "onTalk ? null : treeKey(cur, node)" in tt and "onClick={() => onTalk(treeAsk(node))}" in tt
    assert "/tasks" in dp and "/cc/page/court/" in dp


def test_a_job_that_only_mentions_an_instrument_goes_to_the_centre(tmp_path):
    (tmp_path / "registry").mkdir()
    (tmp_path / "registry" / "systems.json").write_text(json.dumps({"systems": [
        {"id": "hbar.ink", "kind": "instrument"}, {"id": "hbar.music"}]}))
    jobs = [{"id": "J1", "title": "WALL-9 Depth: the wall, like hbar.ink", "started": 1, "ended": None},
            {"id": "J2", "title": "INK-2 Pen", "started": 1, "ended": None, "system": "hbar.ink"},
            {"id": "J3", "title": "SONG-1 hbar.music loops", "started": 1, "ended": None}]
    tl = {t["id"]: t for t in C.board(tmp_path, jobs)["tiles"]}
    assert [j["id"] for j in tl["world"]["jobs"]] == ["J1"]
    assert [j["id"] for j in tl["hbar.ink"]["jobs"]] == ["J2"]                # named as its own system: stays
    assert [j["id"] for j in tl["hbar.music"]["jobs"]] == ["J3"]
