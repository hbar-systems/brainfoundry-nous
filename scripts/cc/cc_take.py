"""cc_take.py: /take, one take from record to demo to ask (DEMO-1, 2026-11-25). The bridge side.

The owner asked for one way to record a verse (or spoken lines) over a track they like, hear it back as a demo
within minutes, and ask the track's artist if they may use it, without a DAW. Three steps on one page
(ui/pages/take.js): record, demo, ask. This module keeps the page's state; the world's own script renders the
demos and drafts the asks (on hbar's brain: scripts/take_demo.py, cron every 2 minutes).

The recording itself is the booth's (cc_booth.py, POST /cc/booth/take): the page sends page.surface = "take" and
what was under the voice in over: {kind: own|file|embed|none, ...}. This module adds, under CC_TAKE_DIR
(default <out>/studio/take):

  backing/<sha12>.<ext> + .json   a track file the owner dropped on the page, kept so the box can mix the demo
  demos/<stem>/demo.json          written by the world's renderer (hbar.take.demo/v1): versions, treatments, MP3s
  demos/<stem>/verdict.json       the owner's press: keep | again | drop, and the treatment kept
  demos/<stem>/ask.want.json      the owner's press "ask the artist"; the renderer answers with ask.json (a draft)
  demos/<stem>/ask.send.json      the owner's press "send", with the text they approved; the renderer sends it
                                  through the owner's own mail door and writes ask.sent.json
  demos/<stem>/ask.answer.json    the artist's answer as the owner marks it (yes | no | a note)

Doors (behind the bridge's page gate like every page route):
  GET  /cc/take                          {ok, takes:[{...booth card, step, demo, verdict, ask, sent}], lines:[sets], films:[...]}
  GET  /cc/take/file?path=<rel>          a demo's MP3, a dropped track, or a film room's cut (cuts/*.mp4) (ranges honoured)
  POST /cc/take/backing                  body = the audio file, X-Take-Name = its name -> {ok, id, name}
  POST /cc/take/verdict {take, word, treatment?}
  POST /cc/take/ask {take, word: draft | send | answer, to?, subject?, body?, answer?, note?}
  POST /cc/take/fetch {video_id, via_mac?, title?}   "use this track": fetch/<id>.want.json for the world's renderer (DEMO-3)

The private library (DEMO-3, 2026-11-25; CC_LIBRARY_DIR): YouTube tracks fetched for his demos, one folder per video
id with a card (track.json: state fetched | demo made | asked | yes | no). GET /cc/take adds library: [...] and
/cc/take/file serves library/<id>/<the fetched file> to the page behind the console sign-in; never after a no.

Lines to read (spoken parts, one take per group) come from the world: <world>/systems/*/ops/take/lines.json
(CC_TAKE_LINES overrides), {sets: [{id, title, treatment, groups: [{n, bar, lines: [...]}], film?: {room, ...}}]}.
Nothing here sends mail, looks anyone up or writes outside CC_TAKE_DIR. Standard library only.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
from pathlib import Path
from urllib.parse import unquote

import cc_extras

MAX_BACKING = 200 * 1024 * 1024
WORDS = ("keep", "again", "drop")
TREATMENTS = ("dry", "chain", "phone")
AUDIO_EXT = re.compile(r"\.(mp3|wav|m4a|aac|flac|ogg|opus|aif|aiff|webm)$", re.I)
TAKE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})_(\d{6})_([a-z0-9][a-z0-9-]{0,59})(\.wav)?")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
OFFER = "[your offer"
VIDEO_RE = re.compile(r"[A-Za-z0-9_-]{11}")


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _read(p: Path):
    try:
        d = json.loads(p.read_text())
        return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None


class Take:
    def __init__(self, booth, root, world: str | None = None, lines: str | None = None, library: str | None = None):
        self.booth = booth
        self.root = Path(root)
        self.library = Path(library) if library else None
        self.world = Path(world) if world else None
        self.lines_path = Path(lines) if lines else None
        self.lock = threading.Lock()

    # ---- where things are
    def _dir(self, sub: str, create: bool = False) -> Path | None:
        d = self.root / sub
        if create:
            try:
                os.makedirs(d, mode=0o2775, exist_ok=True)
            except OSError:
                return None
        return d if d.is_dir() else None

    def line_sets(self) -> list[dict]:
        paths = [self.lines_path] if self.lines_path else (sorted(self.world.glob("systems/*/ops/take/lines.json")) if self.world else [])
        out = []
        for p in paths:
            d = _read(p) if p else None
            for s in (d or {}).get("sets") or []:
                if isinstance(s, dict) and s.get("id") and isinstance(s.get("groups"), list):
                    out.append(s)
        return out

    def _film_rooms(self) -> list[Path]:
        rooms = []
        for s in self.line_sets():
            r = (s.get("film") or {}).get("room")
            if r and Path(r).is_absolute() and Path(r).is_dir():
                rooms.append(Path(r))
        return rooms

    def demo_dir(self, take) -> Path | None:
        """The demo folder of a take by its file or stem; matched on day and time, so a renamed take keeps it."""
        m = TAKE_RE.fullmatch(Path(str(take or "")).name)
        demos = self._dir("demos")
        if not m or demos is None:
            return None
        exact = demos / Path(str(take)).name.removesuffix(".wav")
        if exact.is_dir():
            return exact
        for d in sorted(demos.glob(f"{m.group(1)}_{m.group(2)}_*")):
            if d.is_dir():
                return d
        return None

    # ---- state
    @staticmethod
    def step(card: dict, demo: dict | None, verdict: dict | None, ask: dict | None, sent: dict | None, failed: dict | None) -> dict:
        """Where a take stands on the strip record -> demo -> ask, in one word and a line."""
        over = card.get("over") or {}
        theirs = over.get("kind") in ("embed", "file") and not over.get("mine")
        w = (verdict or {}).get("word")
        if failed and not demo:
            return {"at": "demo", "state": "failed", "say": f"the demo did not render: {failed.get('why', '')}"[:200]}
        if not demo:
            return {"at": "demo", "state": "making", "say": "the demo is being made (a few minutes)"}
        if w == "drop":
            return {"at": "demo", "state": "dropped", "say": "dropped (kept on the box, out of the way)"}
        if w == "again":
            return {"at": "record", "state": "again", "say": "again: record it once more, same track"}
        if w != "keep":
            return {"at": "demo", "state": "ready", "say": "the demo is ready: listen, then keep, again or drop"}
        if not theirs:
            return {"at": "done", "state": "kept", "say": "kept"}
        if sent and sent.get("ok"):
            return {"at": "ask", "state": "sent", "say": f"asked {sent.get('to', '')} on {str(sent.get('at', ''))[:10]}"}
        if sent and not sent.get("ok"):
            return {"at": "ask", "state": "send-failed", "say": f"not sent: {sent.get('why') or sent.get('said') or ''}"[:200]}
        if ask:
            return {"at": "ask", "state": "drafted", "say": "the message is drafted: fill your offer, then send"}
        return {"at": "ask", "state": "to-ask", "say": "kept: ask the artist"}

    def state(self) -> dict:
        b = self.booth.state()
        takes = []
        for c in b.get("takes", []):
            if ((c.get("page") or {}).get("surface")) != "take":
                continue
            d = self.demo_dir(c.get("file"))
            demo = _read(d / "demo.json") if d else None
            verdict = _read(d / "verdict.json") if d else None
            ask = _read(d / "ask.json") if d else None
            sent = _read(d / "ask.sent.json") if d else None
            failed = _read(d / "failed.json") if d else None
            answer = _read(d / "ask.answer.json") if d else None
            wanted = bool(d and (d / "ask.want.json").exists())
            sending = bool(d and (d / "ask.send.json").exists() and not sent)
            st = self.step(c, demo, verdict, ask, sent, failed)
            if wanted and not ask and st["state"] == "to-ask":
                st = {"at": "ask", "state": "drafting", "say": "drafting the message (a few minutes)"}
            if sending:
                st = {"at": "ask", "state": "sending", "say": "sending (within two minutes)"}
            if answer:
                st = {"at": "done", "state": "answered", "say": f"they answered: {answer.get('answer')}"}
            takes.append({**c, "step": st, "demo": demo, "verdict": verdict, "ask": ask, "sent": sent, "answer": answer,
                          "demo_dir": d.name if d else None})
        films = []
        for r in self._film_rooms():
            films.append({"room": str(r), "cuts": (_read(r / "cuts" / "cuts.json") or {}).get("cuts", [])[-5:],
                          "choices": (_read(r / "cuts" / "choices.json") or {}).get("choices", [])})
        return {"ok": True, "dir": str(self.root), "takes": takes, "lines": self.line_sets(), "films": films,
                "library": self.library_state()}

    # ---- the private library (DEMO-3): YouTube tracks fetched for his demos, each with its state
    def library_state(self) -> list[dict]:
        """Every fetched track and where it stands: fetched, demo made, asked, yes, no (and a fetch on its way or
        refused). Read from the library's own cards (written by the world's orfeo_library.py) and fetch/<id>.json."""
        out, seen = [], set()
        lib = self.library if self.library and self.library.is_dir() else None
        for c in sorted(lib.glob("*/track.json")) if lib else []:
            d = _read(c) or {}
            vid = d.get("video_id")
            if not vid:
                continue
            seen.add(vid)
            audio = d.get("audio") if d.get("state") != "no" and (c.parent / str(d.get("audio") or "")).is_file() else None
            out.append({k: d.get(k) for k in ("video_id", "title", "artist", "state", "licence", "claims", "grid",
                                                "fetched_at", "contact", "duration_s", "yes_at", "no_at")}
                       | {"demos": len(d.get("demos") or []), "stems": sorted((d.get("stems") or {}).keys()),
                          "play": f"library/{vid}/{audio}" if audio else None})
        fd = self.root / "fetch"
        for f in sorted(fd.glob("*.json")) if fd.is_dir() else []:
            if f.name.endswith(".want.json"):
                vid = f.name.removesuffix(".want.json")
                if vid not in seen and not (fd / f"{vid}.json").exists():
                    out.append({"video_id": vid, "state": "fetching", "title": (_read(f) or {}).get("title")})
                    seen.add(vid)
                continue
            r = _read(f) or {}
            vid = f.stem
            if vid in seen:
                continue
            want = _read(fd / f"{vid}.want.json") or {}
            if r.get("state") == "refused" and want.get("via_mac") and not r.get("via_mac"):
                out.append({"video_id": vid, "state": "fetching", "title": want.get("title"), "via_mac": True})
            else:
                out.append({"video_id": vid, "state": r.get("state") or "fetching", "title": r.get("title") or want.get("title"),
                            "why": r.get("why"), "via_mac": r.get("via_mac")})
            seen.add(vid)
        return out

    def fetch(self, body: dict) -> tuple[int, dict]:
        """His "use this track": ask the box to fetch it into the library (the world's renderer does, within two
        minutes). via_mac is his press for that one pull through his Mac's home connection, when YouTube refuses the box."""
        body = body or {}
        vid = str(body.get("video_id") or "").strip()
        if not VIDEO_RE.fullmatch(vid):
            return 400, {"ok": False, "error": "a YouTube video id is needed"}
        d = self._dir("fetch", create=True)
        if d is None:
            return 500, {"ok": False, "error": f"the take folder {self.root} cannot be made"}
        lib = self.library / vid / "track.json" if self.library else None
        card = _read(lib) if lib else None
        if card and card.get("state") == "no":
            return 409, {"ok": False, "error": "the artist said no to this track; its copy was deleted"}
        with self.lock:
            self._write(d, f"{vid}.want.json", {"by": "owner", "via_mac": bool(body.get("via_mac")), "at": _now(),
                                           "title": " ".join(str(body.get("title") or "").split())[:200] or None})
        return 200, {"ok": True, "state": "fetching"}

    # ---- files
    def file_path(self, raw) -> Path | None:
        s = str(raw or "").strip()
        if not s or "\x00" in s or "/." in "/" + s:
            return None
        bases = []
        r = self.root
        if not Path(s).is_absolute():
            parts = Path(s).parts
            if parts and parts[0] == "library" and self.library and len(parts) == 3 and VIDEO_RE.fullmatch(parts[1]):
                card = _read(self.library / parts[1] / "track.json") or {}
                if card.get("state") == "no" or parts[2] != card.get("audio"):
                    return None                              # only the fetched copy itself, never after a no
                cand, bases = self.library / parts[1] / parts[2], [self.library]
            elif not parts or parts[0] not in ("demos", "backing"):
                return None
            else:
                cand = r / s
                bases = [r]
        else:
            cand = Path(s)
            bases = [p / "cuts" for p in self._film_rooms()] + [r / "demos", r / "backing"]
        try:
            q = cand.resolve(strict=True)
        except (OSError, RuntimeError):
            return None
        for base in bases:
            try:
                q.relative_to(base.resolve())
            except (OSError, ValueError):
                continue
            if q.is_file() and q.suffix.lower() in (".mp3", ".mp4", ".wav", ".m4a", ".flac", ".ogg", ".opus", ".aif", ".aiff", ".webm", ".aac"):
                return q
        return None

    def serve(self, handler, raw) -> None:
        p = self.file_path(raw)
        if p is None:
            body = b'{"error": "no such take file"}'
            handler.send_response(404)
            handler.send_header("Content-Type", "application/json")
            handler.send_header("Content-Length", str(len(body)))
            handler.send_header("Cache-Control", "no-store")
            handler.end_headers()
            handler.wfile.write(body)
            return
        cc_extras.Files({"take": str(p.parent)}).serve(handler, str(p))

    # ---- presses
    def backing(self, handler) -> tuple[int, dict]:
        name = unquote(handler.headers.get("X-Take-Name", "") or "")[:200].strip() or "track"
        m = AUDIO_EXT.search(name)
        if not m:
            return 400, {"ok": False, "error": "that is not an audio file the page knows (mp3, wav, m4a, flac, ogg, aiff)"}
        data = cc_extras.read_body(handler, MAX_BACKING)
        if not data:
            return 413, {"ok": False, "error": f"a track must be between 1 byte and {MAX_BACKING // (1024 * 1024)} MB"}
        sha = hashlib.sha256(data).hexdigest()
        bid = sha[:16]
        d = self._dir("backing", create=True)
        if d is None:
            return 500, {"ok": False, "error": f"the take folder {self.root} cannot be made"}
        f = d / f"{bid}{m.group(0).lower()}"
        with self.lock:
            if not f.exists():
                tmp = d / f".{bid}.part"
                tmp.write_bytes(data)
                os.chmod(tmp, 0o664)
                tmp.replace(f)
                (d / f"{bid}.json").write_text(json.dumps({"name": name, "sha256": sha, "size": len(data), "kept": _now()}, indent=1) + "\n")
        return 200, {"ok": True, "id": bid, "name": name, "size": len(data)}

    def _write(self, d: Path, name: str, obj: dict) -> None:
        tmp = d / f".{name}.tmp"
        tmp.write_text(json.dumps(obj, indent=1, ensure_ascii=False) + "\n")
        os.chmod(tmp, 0o664)
        tmp.replace(d / name)

    def verdict(self, body: dict) -> tuple[int, dict]:
        d = self.demo_dir((body or {}).get("take"))
        word = str((body or {}).get("word") or "")
        tr = (body or {}).get("treatment")
        if d is None or not (d / "demo.json").exists():
            return 404, {"ok": False, "error": "that take has no demo yet"}
        if word not in WORDS:
            return 400, {"ok": False, "error": "the word is keep, again or drop"}
        if tr is not None and tr not in TREATMENTS:
            return 400, {"ok": False, "error": "the treatment is dry, chain or phone"}
        demo = _read(d / "demo.json") or {}
        ver = (demo.get("versions") or [{}])[-1].get("v")
        with self.lock:
            old = _read(d / "verdict.json")
            v = {"word": word, "treatment": tr, "version": ver, "at": _now()}
            if old:
                v["before"] = {k: old.get(k) for k in ("word", "treatment", "version", "at")}
            self._write(d, "verdict.json", v)
        return 200, {"ok": True, "verdict": v}

    def ask(self, body: dict) -> tuple[int, dict]:
        body = body or {}
        d = self.demo_dir(body.get("take"))
        word = str(body.get("word") or "")
        if d is None or not (d / "demo.json").exists():
            return 404, {"ok": False, "error": "that take has no demo yet"}
        if ((_read(d / "verdict.json") or {}).get("word")) != "keep":
            return 409, {"ok": False, "error": "keep the demo first; the ask goes out only for a kept one"}
        with self.lock:
            if word == "draft":
                if not (d / "ask.want.json").exists():
                    self._write(d, "ask.want.json", {"at": _now()})
                return 200, {"ok": True, "state": "drafting"}
            if word == "send":
                if not (d / "ask.json").exists():
                    return 409, {"ok": False, "error": "there is no draft yet"}
                if (d / "ask.send.json").exists() or (d / "ask.sent.json").exists():
                    return 409, {"ok": False, "error": "this ask is already on its way"}
                to = str(body.get("to") or "").strip()
                subject = " ".join(str(body.get("subject") or "").split())[:200]
                text = str(body.get("body") or "")[:8000]
                if not EMAIL_RE.fullmatch(to):
                    return 400, {"ok": False, "error": "their address is needed (one address)"}
                if not subject or not text.strip():
                    return 400, {"ok": False, "error": "a subject and a message are needed"}
                if OFFER in text:
                    return 400, {"ok": False, "error": "write your offer where it says [your offer], then send"}
                self._write(d, "ask.send.json", {"to": to, "subject": subject, "body": text, "pressed": _now()})
                return 200, {"ok": True, "state": "sending"}
            if word == "answer":
                ans = str(body.get("answer") or "")
                if ans not in ("yes", "no", "talking"):
                    return 400, {"ok": False, "error": "the answer is yes, no or talking"}
                self._write(d, "ask.answer.json", {"answer": ans, "note": str(body.get("note") or "")[:1000], "at": _now()})
                return 200, {"ok": True, "state": "answered"}
        return 400, {"ok": False, "error": "the word is draft, send or answer"}
