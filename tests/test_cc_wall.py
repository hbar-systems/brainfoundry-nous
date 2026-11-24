"""The wall (WALL-1, 2026-11-24): every system live on one dark screen, one small box each.

Pins: GET /cc/systems carries each tile's `said` (the last line of its standing thread; the run's own line while it
answers; asked of the brain again only when the thread moves), the steer door marks a wall turn as said on the wall,
and ui/lib/wall.js under node: the cell's one line, send in place (thread made once, the steer door, a busy thread
takes it in its queue), and a synthetic microphone recorded, transcribed and sent (or kept as a memo when the box
has no speech service). Also the page's wiring and that /systems is untouched by it.

Run from repo root:
    pytest tests/test_cc_wall.py -v
"""
from __future__ import annotations

import importlib.util
import json
import pathlib
import shutil
import subprocess
import sys
import threading

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
import test_cc_steer as S  # noqa: E402   (its bridge fixture: hbar.film's standing thread FILM on the list)

FILM = S.FILM


def _view_bridge(monkeypatch, tmp_path, messages):
    m = S._bridge(monkeypatch, tmp_path)
    asked = []

    def api(method, path, body=None):
        asked.append((method, path))
        if method == "GET" and path == f"/sessions/{FILM}/messages":
            return messages() if callable(messages) else messages
        return {}
    monkeypatch.setattr(m, "_brain_api", api)
    return m, asked


def test_systems_tiles_carry_the_last_line_of_the_standing_thread(monkeypatch, tmp_path):
    hist = {"messages": [{"role": "user", "content": "cut it"},
                         {"role": "assistant", "content": "## Done\nI cut the trailer to 40 s. It is in out/film/trailer.mp4."}]}
    m, asked = _view_bridge(monkeypatch, tmp_path, hist)
    d = m._systems_view()
    tl = {t["id"]: t for t in d["tiles"]}
    s = tl["hbar.film"]["said"]
    assert s["text"] == "It is in out/film/trailer.mp4." and s["live"] is False and s["at"] == "2026-11-23T10:00:00Z"
    assert tl["hbar.music"]["said"] is None                                   # no standing thread yet: still a tile
    # the poll does not ask the brain again until the thread moves
    m._systems_view(); m._systems_view()
    assert asked.count(("GET", f"/sessions/{FILM}/messages")) == 1
    rows = m._threads_load()
    for x in rows:
        if x["brain"] == FILM:
            x["last"] = "2026-11-24T09:00:00Z"
    m._threads_save(rows)
    hist["messages"].append({"role": "assistant", "content": "Second answer, a short one."})
    assert {t["id"]: t for t in m._systems_view()["tiles"]}["hbar.film"]["said"]["text"] == "Second answer, a short one."
    assert asked.count(("GET", f"/sessions/{FILM}/messages")) == 2


def test_said_is_the_runs_own_line_while_it_answers(monkeypatch, tmp_path):
    m, asked = _view_bridge(monkeypatch, tmp_path, {"messages": []})
    r = m.Run(FILM, "cut the trailer")
    monkeypatch.setattr(m, "_run_for_thread", lambda t: r if t == FILM else None)
    monkeypatch.setattr(m, "_run_view", lambda run: {"last": "Reading the K2 master", "waiting": False})
    s = {t["id"]: t for t in m._systems_view()["tiles"]}["hbar.film"]["said"]
    assert s == {"text": "Reading the K2 master", "live": True, "waiting": False, "at": None}
    assert ("GET", f"/sessions/{FILM}/messages") not in asked


def test_said_survives_the_brain_being_down_and_asks_again_later(monkeypatch, tmp_path):
    state = {"up": False}
    m, asked = _view_bridge(monkeypatch, tmp_path, lambda: {"messages": [{"role": "assistant", "content": "Back."}]} if state["up"] else None)
    assert {t["id"]: t for t in m._systems_view()["tiles"]}["hbar.film"]["said"]["text"] == ""
    m._systems_view()
    assert asked.count(("GET", f"/sessions/{FILM}/messages")) == 1        # not every three seconds
    state["up"] = True
    monkeypatch.setattr(m, "SYSTEMS_SAID_RETRY", 0)
    assert {t["id"]: t for t in m._systems_view()["tiles"]}["hbar.film"]["said"]["text"] == "Back."


def test_wall_turn_is_said_on_the_wall_through_the_same_door(monkeypatch, tmp_path):
    m = S._bridge(monkeypatch, tmp_path)
    calls = []
    S._fake_turn(m, monkeypatch, calls)
    st, d = m._steer(FILM, {"message": "cut the trailer", "via": "wall"}, start=lambda f: f())
    assert st == 202 and d["reports_to"] is None
    assert calls[0]["message"] == "(Said on the wall.) cut the trailer" and calls[0]["source"] == "steer"
    st, _ = m._steer(FILM, {"message": "again", "via": "other"}, start=lambda f: f())
    assert calls[1]["message"] == "(Steered from the central chat.) again"


def test_endpoint_field_over_http(monkeypatch, tmp_path):
    m, _ = _view_bridge(monkeypatch, tmp_path, {"messages": [{"role": "assistant", "content": "Two jobs done today."}]})
    srv, base = S._serve(m)
    try:
        st, d = S._call(base + "/systems")
        assert st == 200
        tl = {t["id"]: t for t in d["tiles"]}
        assert tl["hbar.film"]["said"]["text"] == "Two jobs done today." and "said" in tl["hbar.music"]
    finally:
        srv.shutdown()


# ---- ui/lib/wall.js under node ----
def _node(script: str):
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")
    r = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=30, cwd=str(ROOT / "ui" / "lib"))
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.strip().splitlines()[-1])


FAKE = r"""
const W = require('./wall')
// a fake bridge: records every call, answers like the real doors
function bridge(opts) {
  const o = Object.assign({ thread: null, busy: false, queue: 202, stt: 200, heard: 'three loops please' }, opts || {})
  const calls = []
  const res = (status, body) => ({ ok: status >= 200 && status < 300, status, json: async () => body })
  const f = async (url, init) => {
    const body = init && typeof init.body === 'string' ? JSON.parse(init.body) : (init && init.body ? { form: init.body.parts } : null)
    calls.push({ url, body })
    if (url === '/cc/systems/thread') { const created = !o.thread; o.thread = o.thread || 'f0000000-0000-4000-8000-000000000002'; return res(200, { ok: true, thread: o.thread, created }) }
    if (/\/say$/.test(url)) { if (o.busy) { o.busy = o.busyOnce ? false : o.busy; return res(409, { ok: false, busy: true, error: 'busy' }) } return res(202, { ok: true }) }
    if (url === '/cc/queue') return res(o.queue, o.queue === 202 ? { ok: true } : { error: 'idle' })
    if (url === '/cc/transcribe') return o.stt === 200 ? res(200, { ok: true, text: o.heard }) : res(o.stt, { ok: false, error: 'no stt' })
    if (url.startsWith('/cc/systems/voice')) return res(200, { ok: true, path: '/in/2026-11-24/memo_hbar.film_x.webm' })
    return res(404, {})
  }
  return { f, calls, o }
}
class FD { constructor() { this.parts = [] } append(k, v, n) { this.parts.push([k, n]) } }
"""


def test_cell_line_and_state():
    d = _node(FAKE + r"""
const run = { detail: { running: { lines: [{ text: 'render the K2 trailer' }] } }, counts: { running: 2 } }
console.log(JSON.stringify({
  live: W.cellLine({ said: { live: true, text: '  Reading\n the master ' } }, { text: 'x', state: 'sent' }),
  thinking: W.cellLine({ said: { live: true, text: '' } }),
  waits: W.cellLine({ said: { live: true, waiting: true, text: 'a card' } }),
  sent: W.cellLine({ said: { text: 'old' } }, { text: 'cut it', state: 'sent' }),
  job: W.cellLine({ ...run, said: { text: 'old answer' } }),
  said: W.cellLine({ said: { text: 'old answer' } }),
  quiet: W.cellLine({ id: 'self' }),
  st: [W.cellState(run), W.cellState({ said: { live: true } }), W.cellState({})],
  over: [W.sentOver({ at: 0, before: 'a' }, { said: { at: 'a' } }, 1000), W.sentOver({ at: 0, before: 'a' }, { said: { at: 'b' } }, 1000),
         W.sentOver({ at: 0, before: 'a' }, { said: { live: true } }, 1000), W.sentOver({ at: 0 }, {}, 61000)],
}))
""")
    assert d["live"] == {"text": "Reading the master", "kind": "live"}
    assert d["thinking"]["text"] == "thinking" and d["waits"]["kind"] == "waits"
    assert d["sent"] == {"text": "cut it", "kind": "sent"} and d["job"] == {"text": "render the K2 trailer", "kind": "job"}
    assert d["said"] == {"text": "old answer", "kind": "said"} and d["quiet"]["kind"] == "quiet"
    assert d["st"] == [{"running": 2, "on": True}, {"running": 0, "on": True}, {"running": 0, "on": False}]
    assert d["over"] == [False, True, True, True]


def test_send_in_place_makes_the_thread_once_and_uses_the_steer_door():
    d = _node(FAKE + r"""
;(async () => {
  const a = bridge()
  const r1 = await W.sendText(a.f, 'hbar.film', '  cut the trailer ', null)
  const r2 = await W.sendText(a.f, 'hbar.film', 'and a still', r1.thread)
  const b = bridge({ thread: 'f0000000-0000-4000-8000-000000000002', busy: true })
  const r3 = await W.sendText(b.f, 'hbar.film', 'later', 'f0000000-0000-4000-8000-000000000002')
  const c = bridge({ thread: 't', busy: true, busyOnce: true, queue: 409 })
  const r4 = await W.sendText(c.f, 'hbar.film', 'now', 't')
  const e = await W.sendText(a.f, 'hbar.film', '   ', null)
  const bad = await W.sendText(a.f, 'Not An Id', 'x', null)
  const down = await W.sendText(async () => { throw new Error('x') }, 'hbar.film', 'x', null)
  console.log(JSON.stringify({ r1, r2, a: a.calls, r3, b: b.calls.map(x => x.url), r4, c: c.calls.map(x => x.url), e, bad, down }))
})()
""")
    assert d["r1"]["ok"] and d["r1"]["created"] is True
    assert [c["url"] for c in d["a"]] == ["/cc/systems/thread", "/cc/threads/f0000000-0000-4000-8000-000000000002/say",
                                          "/cc/threads/f0000000-0000-4000-8000-000000000002/say"]   # made once, then reused
    assert d["a"][1]["body"] == {"message": "cut the trailer", "via": "wall"} and d["r2"]["ok"]
    assert d["r3"]["ok"] and d["r3"]["queued"] and d["b"][-1] == "/cc/queue"
    assert d["r4"]["ok"] and d["c"] == ["/cc/threads/t/say", "/cc/queue", "/cc/threads/t/say"]
    assert not d["e"]["ok"] and not d["bad"]["ok"] and d["down"] == {"ok": False, "error": "the bridge did not answer"}


def test_synthetic_mic_records_transcribes_and_sends():
    d = _node(FAKE + r"""
// a synthetic microphone: getUserMedia gives a stream whose track records its stop; MediaRecorder emits two chunks
const tracks = []
const mediaDevices = { getUserMedia: async () => { const t = { stopped: false, stop() { this.stopped = true } }; tracks.push(t); return { getTracks: () => [t] } } }
class MR {
  static isTypeSupported(m) { return m === 'audio/webm' }
  constructor(stream, o) { this.mimeType = (o && o.mimeType) || ''; this.state = 'inactive' }
  start() { this.state = 'recording'; this.ondataavailable({ data: { size: 3 } }); this.ondataavailable({ data: { size: 0 } }) }
  stop() { this.state = 'inactive'; this.ondataavailable({ data: { size: 4 } }); setTimeout(() => this.onstop && this.onstop(), 5) }
}
class B { constructor(parts, o) { this.parts = parts.length; this.type = o.type } }
;(async () => {
  const rec = new W.Recorder({ mediaDevices, MediaRecorder: MR, Blob: B })
  const started = await rec.start()
  const busy = rec.busy
  const blob = await rec.stop()
  const a = bridge({ thread: 'f0000000-0000-4000-8000-000000000002' })
  const sent = await W.sendClip(a.f, 'hbar.film', blob, 'f0000000-0000-4000-8000-000000000002', FD)
  const n = bridge({ thread: 't', stt: 409 })
  const memo = await W.sendClip(n.f, 'hbar.film', blob, 't', FD)
  const none = await new W.Recorder({}).start()
  const denied = await new W.Recorder({ mediaDevices: { getUserMedia: async () => { throw new Error('no') } }, MediaRecorder: MR }).start()
  const r2 = new W.Recorder({ mediaDevices, MediaRecorder: MR, Blob: B }); await r2.start(); r2.drop()
  console.log(JSON.stringify({ started, busy, after: rec.busy, blob, tracks: tracks.map(t => t.stopped), sent, a: a.calls, memo,
    n: n.calls.map(x => x.url), none, denied, dropped: r2.busy, names: [W.clipName({ type: 'audio/mp4' }), W.clipName({ type: 'audio/ogg' }), W.clipName({})] }))
})()
""")
    assert d["started"] == {"ok": True} and d["busy"] is True and d["after"] is False
    assert d["blob"] == {"parts": 2, "type": "audio/webm"} and d["tracks"] == [True, True]     # the microphone is let go
    assert d["sent"]["ok"] and d["sent"]["heard"] == "three loops please"
    assert [c["url"] for c in d["a"]] == ["/cc/transcribe", "/cc/threads/f0000000-0000-4000-8000-000000000002/say"]
    assert d["a"][0]["body"] == {"form": [["file", "clip.webm"]]}
    assert d["a"][1]["body"] == {"message": "three loops please", "via": "wall"}
    assert d["memo"] == {"ok": True, "memo": "/in/2026-11-24/memo_hbar.film_x.webm"}
    assert d["n"] == ["/cc/transcribe", "/cc/systems/voice?system=hbar.film"]
    assert d["none"]["error"] == "this browser cannot record" and "not allowed" in d["denied"]["error"] and d["dropped"] is False
    assert d["names"] == ["clip.m4a", "clip.ogg", "clip.webm"]


def test_wall_page_wiring_and_systems_untouched():
    w = (ROOT / "ui" / "pages" / "wall.js").read_text()
    assert "from '../lib/wall'" in w and "fetch(systemsUrl(depthRef.current), { cache: 'no-store' })" in w   # /cc/systems; ?depth= while a layer is open (WALL-3)
    assert "setInterval(load, 3000)" in w and "document.visibilityState === 'visible'" in w       # none while hidden
    assert "sendText(fetch, sid, text, threadOf(sid))" in w and "sendClip(fetch, sid, blob, threadOf(sid))" in w
    assert "/talk?pane=wall-" in w and "router" not in w and "location.href" not in w             # never navigates
    assert "<Head><title>Wall</title></Head>" in w
    assert not (ROOT / "ui" / "pages" / "wall").exists()                                         # one /wall route
    sy = (ROOT / "ui" / "pages" / "systems" / "index.js").read_text()
    assert "lib/wall" not in sy
