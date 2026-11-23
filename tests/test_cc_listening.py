"""YT-2 (2026-11-23): "Bring your listening" (scripts/cc/cc_listening.py) against a stand-in One and brain.
Checks: only GET reads through one-read, likes and playlists deduplicated into one record per video, the taste
note written and kept through permit -> upload -> approve, a flagged scan left waiting, no One = no reads."""
import json, os, stat, sys, threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "cc"))
import cc_listening  # noqa: E402

FAKE_ONE = r'''#!/usr/bin/env python3
import json, sys, os
log = os.environ["FAKE_LOG"]; open(log, "a").write(" ".join(sys.argv[1:]) + "\n")
if sys.argv[1:3] == ["--agent", "list"]:
    print(json.dumps({"connections": [{"platform": "youtube-data", "state": "operational", "key": "live::youtube-data::default::abc123"},
                                      {"platform": "gmail", "state": "operational", "key": "g"}]})); sys.exit()
action, q = sys.argv[2], json.loads(sys.argv[sys.argv.index("--query-params") + 1])
A = {v: k for k, v in json.loads(os.environ["FAKE_ACTIONS"]).items()}[action]
def item(v, at): return {"snippet": {"resourceId": {"videoId": v}, "publishedAt": at + "T00:00:00Z", "title": v}}
if A == "channels": r = {"items": [{"snippet": {"title": "Maria", "customUrl": "@maria"}}]}
elif A == "playlists": r = {"items": [{"id": "PL1", "snippet": {"title": "BEATS 1"}}, {"id": "PL2", "snippet": {"title": "deep house"}}]}
elif A == "items":
    r = {"LL": {"items": [item("v1", "2026-11-01"), item("v2", "2026-11-02")]},
         "PL1": {"items": [item("v2", "2026-10-01"), item("v3", "2026-10-02")]},
         "PL2": {"items": [item("v4", "2026-09-01")]}}[q["playlistId"]]
elif A == "videos":
    meta = {"v1": ("Artist A - Song (Extended Mix)", "Artist A - Topic", "10", "PT6M"), "v2": ("Boom Bap Type Beat 90 BPM", "Beatmaker", "10", "PT2M30S"),
            "v3": ("A cooking video", "Chef", "26", "PT9M"), "v4": ("Sunset", "DJ B", "10", "PT1H2M")}
    r = {"items": [{"id": v, q["part"]: ({"title": meta[v][0], "channelTitle": meta[v][1], "categoryId": meta[v][2]} if q["part"] == "snippet" else {"duration": meta[v][3]})} for v in q["id"].split(",")]}
elif A == "cats": r = {"items": [{"id": "10", "snippet": {"title": "Music"}}, {"id": "26", "snippet": {"title": "Howto & Style"}}]}
print(json.dumps({"response": r}))
'''


class Brain(BaseHTTPRequestHandler):
    seen, risk = [], "none"

    def log_message(self, *a): pass

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0)); body = self.rfile.read(n)
        Brain.seen.append((self.path, self.headers.get("X-API-Key"), body))
        out = {"/documents/upload/permit": (200, {"permit_id": "p1"}),
               "/documents/approve-all": (200, {"running": True})}.get(self.path)
        if self.path == "/documents/upload":
            if b'name="layer"\r\n\r\nepisodic' in body:
                out = (400, {"error": {"message": "Unknown layer 'episodic'. Defined layers: ['semantic']"}})
            else:
                out = (202, {"proposal_id": "prop1", "injection_scan": {"risk": Brain.risk}})
        code, j = out
        self.send_response(code); self.send_header("Content-Type", "application/json"); self.end_headers()
        self.wfile.write(json.dumps(j).encode())


def setup(tmp, monkeypatch, risk="none"):
    one = tmp / "one"; one.write_text(FAKE_ONE); one.chmod(one.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("FAKE_LOG", str(tmp / "calls.log")); monkeypatch.setenv("FAKE_ACTIONS", json.dumps(cc_listening.ACTIONS))
    monkeypatch.setenv("ONE_SECRET", "x")
    Brain.seen, Brain.risk = [], risk
    srv = HTTPServer(("127.0.0.1", 0), Brain); threading.Thread(target=srv.serve_forever, daemon=True).start()
    L = cc_listening.Listening(tmp / "listening", one_read=str(one), one_bin=str(one),
                               api_url=f"http://127.0.0.1:{srv.server_port}", api_key="k")
    # one-read is "one-read youtube-data <action> <key> ..."; the fake reads argv[2] as the action
    return L, srv


def test_read_dedupes_and_keeps_note(tmp_path, monkeypatch):
    L, srv = setup(tmp_path, monkeypatch)
    last = L.read(); srv.shutdown()
    assert last["records"] == 4 and last["accounts"] == [{"channel": "Maria", "likes": 2, "playlists": 2, "items": 3}]
    recs = {r["video_id"]: r for r in map(json.loads, (tmp_path / "listening/records.jsonl").read_text().splitlines())}
    assert recs["v2"]["liked"] and recs["v2"]["playlists"] == ["BEATS 1"] and len(recs["v2"]["added"]) == 2
    assert recs["v1"]["artist"] == "Artist A" and recs["v2"]["bpm"] == 90 and recs["v4"]["seconds"] == 3720
    assert not recs["v3"]["music"] and recs["v4"]["music"]
    note = (tmp_path / "listening/taste.md").read_text()
    assert "Music I like" in note and "deep house" in note and "boom bap" in note and "90 BPM" in note
    assert last["note"]["kept"] and last["note"]["layer"] == "semantic"   # episodic refused -> next defined layer
    paths = [p for p, _, _ in Brain.seen]
    assert paths.count("/documents/approve-all") == 1 and all(k == "k" for _, k, _ in Brain.seen)
    calls = (tmp_path / "calls.log").read_text().splitlines()
    assert all(c.startswith("youtube-data conn_mod_def::") or c.startswith("--agent list") for c in calls)
    assert not any("execute" in c or "POST" in c for c in calls)


def test_flagged_scan_waits(tmp_path, monkeypatch):
    L, srv = setup(tmp_path, monkeypatch, risk="high")
    last = L.read(); srv.shutdown()
    assert not last["note"]["kept"] and "waiting" in last["note"]["why"]
    assert "/documents/approve-all" not in [p for p, _, _ in Brain.seen]


def test_no_one_no_reads(tmp_path, monkeypatch):
    monkeypatch.delenv("ONE_SECRET", raising=False)
    L = cc_listening.Listening(tmp_path / "l", one_read=str(tmp_path / "missing"))
    st = L.state()
    assert st["one"] is False and st["accounts"] == [] and set(st["disclosure"]) == {"en", "el", "ru"}
    assert L.start()[0] == 400


def test_bridge_wires_routes():
    src = (Path(__file__).resolve().parent.parent / "scripts/cc/cc-bridge.py").read_text()
    assert 'route == "/listening"' in src and 'route == "/listening/read"' in src and "import cc_listening" in src
