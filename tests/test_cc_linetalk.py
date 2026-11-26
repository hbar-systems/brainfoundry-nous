"""Line talk (LINE-TALK-1, 2026-11-25): press a line of an answer and keep talking about it; read a thread from the wall.

hbar: "if i can click the line say the line say, 'The court: ' -- and this automatically either does what the ask
button does or what note does.. but point is by clicking i can continue to talk without needing to press too much".
And: "how can we read thread thru wall? like something pop out?". And the centre showed "ran: python3
scripts/continue.py ..." while working, which tells him nothing.

Pins, without a browser (tests/browser/test_line_talk.py presses the real pages):
  - ui/lib/linetalk.js under node: one line, the wall's About-this message (filled slots only, one message), plain
    words for a tool call (from its description, never the command), and the same words as the bridge's
    cc_extras.tool_plain for a table of calls.
  - ui/lib/wall.js under node: the last answer of a thread (markers stripped, a hand-back skipped), transcribe (into
    words, never sent), the columns address (the open one first, the centre never a column, four at most), the kept
    view and the bridge told.
  - the bridge: a running turn's live line is the plain words; POST /cc/view notes one line per switch, refuses
    anything but wall or columns, and needs the console's token like every other door.
  - the pages' wiring: the chat routes dictation into a slot, the wall opens the card from a line and keeps Esc, the
    systems page carries the switch back.

Run from repo root:
    pytest tests/test_cc_linetalk.py -v
"""
from __future__ import annotations

import importlib.util
import json
import pathlib
import shutil
import subprocess
import sys
import urllib.error
import urllib.request

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "scripts" / "cc"))
import cc_extras  # noqa: E402
import test_cc_steer as S  # noqa: E402

UI = ROOT / "ui"


def _node(script: str):
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")
    r = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=30, cwd=str(UI / "lib"))
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.strip().splitlines()[-1])


CALLS = [
    ("Bash", {"command": "python3 scripts/continue.py --thread world", "description": "Read the handoff"}),
    ("Bash", {"command": "python3 scripts/jobs.py", "description": "Check jobs"}),
    ("Bash", {"command": "git status --short", "description": "Show working tree status"}),
    ("Bash", {"command": "ls -la", "description": "List files in the out folder"}),
    ("Bash", {"command": "npm run build", "description": "Run the build"}),
    ("Bash", {"command": "sleep 3", "description": "Wait for the preview"}),
    ("Bash", {"command": "rm -rf /tmp/x"}),
    ("Read", {"file_path": "/home/hands/world/ops/2026-11-24_continue-handoff.md"}),
    ("Edit", {"file_path": "/x/ui/pages/wall.js"}),
    ("Write", {"file_path": "/x/REPORT.md"}),
    ("Grep", {"pattern": "secret.*token"}),
    ("Agent", {"description": "Map the tests", "prompt": "..."}),
    ("WebFetch", {"url": "https://example.invalid"}),
    ("mcp__claude_ai_Gmail__search", {}),
    ("TodoWrite", {}),
    ("Skill", {}),
]


def test_plain_words_never_show_the_command_and_match_the_bridge():
    js = _node("const L = require('./linetalk'); console.log(JSON.stringify(" + json.dumps(CALLS) + ".map(([n, i]) => L.plainStep(n, i))))")
    py = [cc_extras.tool_plain(n, i) for n, i in CALLS]
    assert js == py
    assert py[:6] == ["reading the handoff", "checking jobs", "showing working tree status", "listing files in the out folder",
                      "running the build", "waiting for the preview"]
    assert py[6] == "running a command"                                   # no description: never the raw command
    assert py[7] == "reading 2026-11-24_continue-handoff.md" and py[8] == "editing wall.js" and py[9] == "writing REPORT.md"
    assert py[10] == "searching the files" and py[11] == "a helper: mapping the tests"
    assert py[13] == "using claude ai Gmail" and py[14] == "updating the plan" and py[15] == "using Skill"
    for (n, i), s in zip(CALLS, py):
        assert "python3" not in s and "rm -rf" not in s and "/home/" not in s and "secret" not in s


def test_about_block_and_one_line():
    d = _node(r"""
const L = require('./linetalk')
console.log(JSON.stringify({
  sq: L.squash('  The   court:\n three  rulings  '),
  long: L.squash('x'.repeat(400)).length,
  one: L.aboutBlock([{ quote: 'The court: three rulings', text: ' take the first ' }]),
  two: L.aboutBlock([{ quote: 'A', text: 'one' }, { quote: 'B', text: '' }, { quote: 'C', text: 'three' }]),
  none: L.aboutBlock([{ quote: 'A', text: '  ' }]),
  g: ['run', 'make', 'check', 'tie', 'continue', 'commit', 'reading'].map(L.gerund),
  hold: L.HOLD_MS,
}))""")
    assert d["sq"] == "The court: three rulings" and d["long"] == 300
    assert d["one"] == 'About this: "The court: three rulings" - take the first'
    assert d["two"] == 'About this: "A" - one\n\nAbout this: "C" - three'      # every filled slot, one message
    assert d["none"] == ""
    assert d["g"] == ["running", "making", "checking", "tying", "continuing", "committing", "reading"]
    assert d["hold"] == 500


WALL = r"""
const W = require('./wall')
const res = (status, body) => ({ ok: status >= 200 && status < 300, status, json: async () => body })
function fake(routes) {
  const calls = []
  const f = async (url, opts) => { calls.push({ url, method: (opts && opts.method) || 'GET', body: opts && typeof opts.body === 'string' ? JSON.parse(opts.body) : null }); const r = routes(url, opts); if (r instanceof Error) throw r; return r }
  f.calls = calls
  return f
}
class FD { constructor() { this.parts = [] } append(k, v, n) { this.parts.push([k, n]) } }
function store() { const m = {}; return { getItem: k => (k in m ? m[k] : null), setItem: (k, v) => { m[k] = String(v) }, m } }
"""


def test_last_answer_transcribe_and_the_view_switch():
    d = _node(WALL + r"""
;(async () => {
  const hist = { messages: [
    { role: 'user', content: 'go' },
    { role: 'assistant', content: '- **The court:** three rulings\n- the trailer\n\n<tree>{"nodes": []}</tree>\n<steer>{"system": "hbar.film", "say": "x"}</steer>', created_at: '2026-11-25T10:00:00Z' },
    { role: 'assistant', content: '[agent report received: FILM-2]' },
  ] }
  const f1 = fake(url => (url.startsWith('/api/bf/sessions/') ? res(200, hist) : res(404, {})))
  const a = await W.lastAnswer(f1, 'T-1')
  const b = await W.lastAnswer(fake(() => res(200, { messages: [{ role: 'user', content: 'hi' }] })), 'T-2')
  const c = await W.lastAnswer(fake(() => res(502, {})), 'T-3')
  const e = await W.lastAnswer(fake(() => new Error('down')), 'T-4')
  const n = await W.lastAnswer(fake(() => res(200, {})), null)
  const blob = { type: 'audio/webm' }
  const t1 = fake(() => res(200, { ok: true, text: ' the first one ' }))
  const tr = await W.transcribe(t1, blob, FD)
  const tr0 = await W.transcribe(fake(() => res(200, { ok: true, text: '' })), blob, FD)
  const tr9 = await W.transcribe(fake(() => res(409, { ok: false })), blob, FD)
  const s = store()
  const v0 = W.readView(s)
  const vf = fake(() => res(200, { ok: true }))
  await W.switchView(vf, s, 'columns', 'wall')
  const v1 = W.readView(s)
  const bad = await W.switchView(vf, s, 'grid', 'wall')
  const down = await W.switchView(fake(() => new Error('down')), s, 'wall', 'columns')
  console.log(JSON.stringify({ a, b, c, e, n, url: f1.calls[0].url, tr, tr0, tr9, trCalls: t1.calls.map(x => x.url),
    v0, v1, v2: W.readView(s), bad, down, viewCalls: vf.calls,
    cols: [W.columnsUrl(['hbar.film', 'world', 'hbar.music', 'hbar.art', 'hbar.blog', 'hbar.ink'], 'hbar.ink'), W.columnsUrl([], null), W.columnsUrl(['../x', 'hbar.film'], 'world')],
  }))
})()""")
    assert d["url"] == "/api/bf/sessions/T-1/messages"
    assert d["a"]["text"] == "- **The court:** three rulings\n- the trailer" and d["a"]["at"] == "2026-11-25T10:00:00Z"   # markers out, hand-back skipped
    assert d["b"] == {"error": "nothing said in this thread yet"} and d["c"] == {"error": "the brain answered 502"}
    assert d["e"] == {"error": "the brain did not answer"} and d["n"] == {"error": "no thread here yet"}
    assert d["tr"] == {"ok": True, "text": "the first one"} and d["trCalls"] == ["/cc/transcribe"]      # words only, nothing sent
    assert d["tr0"]["ok"] is False and "no speech service" in d["tr9"]["error"]
    assert d["v0"] is None and d["v1"] == "columns" and d["v2"] == "wall"
    assert d["bad"] == {"ok": False} and d["down"] == {"ok": True}
    assert d["viewCalls"] == [{"url": "/cc/view", "method": "POST", "body": {"view": "columns", "from": "wall"}}]
    assert d["cols"] == ["/systems?open=hbar.ink,hbar.film,hbar.music,hbar.art", "/systems", "/systems?open=hbar.film"]


def _bridge(monkeypatch, tmp_path, token=""):
    monkeypatch.setenv("CC_VIEWS_LOG", str(tmp_path / "board" / "views.jsonl"))
    return S._bridge(monkeypatch, tmp_path, token)


def test_live_line_is_plain_words(monkeypatch, tmp_path):
    m = _bridge(monkeypatch, tmp_path)
    r = m.Run("T-1", "go")
    inp = {"command": "python3 scripts/continue.py --thread world", "description": "Read the handoff"}
    r.emit("tool", {"name": "Bash", "brief": m._tool_brief("Bash", inp), "plain": cc_extras.tool_plain("Bash", inp)})
    v = m._run_view(r)
    assert v["last"] == "reading the handoff"
    r2 = m.Run("T-2", "go")
    r2.emit("tool", {"name": "Bash", "brief": "ran: ls"})                   # an event from before: still a line
    assert m._run_view(r2)["last"] == "ran: ls"
    src = (ROOT / "scripts" / "cc" / "cc-bridge.py").read_text()
    assert '"plain": cc_extras.tool_plain(blk.get("name"), blk.get("input"))' in src


def test_view_door_notes_each_switch(monkeypatch, tmp_path):
    m = _bridge(monkeypatch, tmp_path, token="tok")
    assert m._view_note({"view": "columns", "from": "wall"})[0] == 200
    assert m._view_note({"view": "wall", "from": "nonsense"})[0] == 200
    assert m._view_note({"view": "grid"})[0] == 400 and m._view_note(None)[0] == 400
    rows = [json.loads(x) for x in (tmp_path / "board" / "views.jsonl").read_text().splitlines()]
    assert [(r["view"], r["from"]) for r in rows] == [("columns", "wall"), ("wall", None)]
    assert all(r["ts"].endswith("Z") for r in rows)
    assert oct((tmp_path / "board" / "views.jsonl").stat().st_mode & 0o777) == "0o664"
    srv, base = S._serve(m)
    try:
        req = urllib.request.Request(base + "/view", data=b'{"view":"wall"}', method="POST", headers={"Content-Type": "application/json"})
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(req, timeout=5)
        assert e.value.code == 403                                          # the console's token, like every door
    finally:
        srv.shutdown()
    assert len((tmp_path / "board" / "views.jsonl").read_text().splitlines()) == 2


def test_pages_are_wired():
    cc = (UI / "pages" / "cc.js").read_text()
    assert "import LineSlot, { LINE_SLOT_CSS } from '../components/LineSlot'" in cc
    assert "putTalk([st.base, st.finals, interim.trim()].filter(Boolean).join(' '))" in cc       # dictation can go to a slot
    assert "if (to) { setNote(to, t);" in cc                                                     # a slot's words are never sent by themselves
    assert "const margin = notes.filter(n => n.kind !== 'line')" in cc
    assert "'the line I pressed'" in cc
    wall = (UI / "pages" / "wall.js").read_text()
    assert "<WallRead key={reading}" in wall and "onRead={onRead}" in wall and '<ViewSwitch view="wall"' in wall
    assert "readView(store) === 'columns'" in wall
    sy = (UI / "pages" / "systems" / "index.js").read_text()
    assert '<ViewSwitch view="columns"' in sy and "switchView(fetch, store, 'wall', 'columns')" in sy
    orbit = (UI / "components" / "WallOrbit.js").read_text()
    assert orbit.count("onRead={onRead ? () => onRead(CENTRE) : null}") == 1   # WALL-6: the centre's box stays out, one line
