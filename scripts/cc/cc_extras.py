"""cc_extras: files, jobs and uploads for the CC bridge. Created 2026-09-22.

Imported by cc-bridge.py (same directory). Standard library only.

- Files: list and stream files from a fixed set of roots (the work clones, the mirror,
  the reasoner's out/ and in/ folders, the brain repo). Paths are resolved and must
  stay inside a root; range requests are honoured so audio and video can seek.
- Jobs: commands that outlive a turn. Started detached (own session), logged to
  out/jobs/<id>.log, recorded in out/jobs/jobs.json. Nothing here runs sudo.
- Uploads: multipart bodies from the page, saved under in/<date>/, size-capped.
"""
from __future__ import annotations

import email.parser
import email.policy
import json
import mimetypes
import os
import re
import shlex
import subprocess
import threading
import time
from pathlib import Path

MAX_UPLOAD = 50 * 1024 * 1024
TEXT_SUFFIXES = {".md", ".txt", ".json", ".py", ".js", ".ts", ".sh", ".yml", ".yaml", ".toml", ".csv", ".tsv", ".log", ".css", ".ini", ".cfg"}
KIND_BY_SUFFIX = {
    **{s: "audio" for s in (".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aiff", ".aif")},
    **{s: "video" for s in (".mp4", ".webm", ".mov", ".m4v")},
    **{s: "image" for s in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg")},
    ".pdf": "pdf", ".html": "html", ".htm": "html",
}


class Files:
    def __init__(self, roots: dict[str, str]):
        # label -> absolute path; only existing directories count
        self.roots = {k: Path(v).resolve() for k, v in roots.items() if v and Path(v).is_dir()}

    def resolve(self, raw: str) -> Path | None:
        """A path inside one of the roots, or None. Symlinks are followed before the check."""
        if not raw:
            return None
        try:
            p = Path(raw).expanduser().resolve()
        except Exception:
            return None
        for root in self.roots.values():
            try:
                p.relative_to(root)
                return p
            except ValueError:
                continue
        return None

    @staticmethod
    def kind(p: Path) -> str:
        s = p.suffix.lower()
        if s in KIND_BY_SUFFIX:
            return KIND_BY_SUFFIX[s]
        if s in TEXT_SUFFIXES or not s:
            return "text"
        return "other"

    def listing(self, raw: str | None) -> dict:
        if not raw:
            return {"path": None, "roots": [{"label": k, "path": str(v)} for k, v in self.roots.items()], "entries": []}
        p = self.resolve(raw)
        if p is None or not p.exists():
            return {"error": "not a path the reasoner can reach"}
        if p.is_file():
            st = p.stat()
            return {"path": str(p), "file": True, "size": st.st_size, "mtime": int(st.st_mtime), "kind": self.kind(p)}
        entries = []
        try:
            for c in sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
                if c.name.startswith(".") and c.name not in (".hbar",):
                    continue
                try:
                    st = c.stat()
                except OSError:
                    continue
                entries.append({"name": c.name, "dir": c.is_dir(), "size": 0 if c.is_dir() else st.st_size,
                                "mtime": int(st.st_mtime), "kind": "dir" if c.is_dir() else self.kind(c)})
        except PermissionError:
            return {"error": "no permission to read this folder"}
        parent = str(p.parent) if self.resolve(str(p.parent)) else None
        return {"path": str(p), "parent": parent, "entries": entries[:2000],
                "roots": [{"label": k, "path": str(v)} for k, v in self.roots.items()]}

    # Files the person may rewrite from the console (2026-09-28): text inside the world, out or in,
    # never the brain repo, never .env or anything under .git, never a secret. A silent save: the
    # person's own edit of the person's own file needs no permit. Written atomically; group-writable
    # so the hands (a different user after the split) can rewrite what the bridge wrote.
    WRITE_ROOTS = ("world", "out", "in", "work")
    NEVER_NAMES = (".env", ".env.local", ".env.example", "git-credentials", ".netrc")
    WRITE_MAX = 4_000_000

    def writable(self, raw: str) -> tuple[Path | None, str]:
        p = self.resolve(raw)
        if p is None:
            return None, "not a path the reasoner can reach"
        if not any(p == r or r in p.parents for k, r in self.roots.items() if k in self.WRITE_ROOTS):
            return None, "only files in the world, out or in can be edited here"
        parts = p.parts
        if ".git" in parts or any(n in self.NEVER_NAMES or n.endswith(".secret") or n.endswith(".pem") or n.endswith(".key") for n in parts):
            return None, "not editable here: secrets and git internals stay closed"
        if p.exists() and not p.is_file():
            return None, "that is a folder"
        if self.kind(p) != "text":
            return None, "only text files are edited here"
        return p, ""

    def write(self, raw: str, text: str, expect_mtime: int | None = None) -> dict:
        p, why = self.writable(raw)
        if p is None:
            return {"ok": False, "error": why}
        if len(text.encode("utf-8")) > self.WRITE_MAX:
            return {"ok": False, "error": "too large to save from here"}
        if expect_mtime is not None and p.exists() and int(p.stat().st_mtime) != int(expect_mtime):
            return {"ok": False, "error": "changed on disk since you opened it; reload, then edit again", "conflict": True,
                    "mtime": int(p.stat().st_mtime)}
        if not p.parent.is_dir():
            return {"ok": False, "error": "the folder does not exist"}
        tmp = p.parent / f".{p.name}.saving-{os.getpid()}"
        try:
            tmp.write_text(text, encoding="utf-8")
            try:
                os.chmod(tmp, 0o664)
            except OSError:
                pass
            os.replace(tmp, p)
        except OSError as e:
            try:
                tmp.unlink()
            except OSError:
                pass
            return {"ok": False, "error": f"could not save: {e.strerror or e}"}
        st = p.stat()
        return {"ok": True, "path": str(p), "size": st.st_size, "mtime": int(st.st_mtime)}

    def recent(self, root_label: str = "out", n: int = 30) -> list:
        """Newest files under one root (the reasoner's outputs by default), for the pane's
        first view: what was just made, without hunting through folders."""
        root = self.roots.get(root_label)
        if root is None:
            return []
        found = []
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if not d.startswith(".") and d != "jobs"]
            for fn in filenames:
                if fn.startswith("."):
                    continue
                fp = Path(dirpath) / fn
                try:
                    st = fp.stat()
                except OSError:
                    continue
                found.append((st.st_mtime, fp, st.st_size))
        found.sort(key=lambda x: -x[0])
        return [{"path": str(fp), "name": fp.name, "dir": str(fp.parent), "size": sz, "mtime": int(mt), "kind": self.kind(fp)}
                for mt, fp, sz in found[:n]]

    def serve(self, handler, raw: str) -> None:
        """Stream a file with the right type; honour a single byte range."""
        p = self.resolve(raw)
        if p is None or not p.is_file():
            body = b'{"error": "not a file the reasoner can reach"}'
            handler.send_response(404); handler.send_header("Content-Type", "application/json")
            handler.send_header("Content-Length", str(len(body))); handler.end_headers(); handler.wfile.write(body)
            return
        size = p.stat().st_size
        ctype = mimetypes.guess_type(p.name)[0] or ("text/plain; charset=utf-8" if self.kind(p) == "text" else "application/octet-stream")
        start, end = 0, size - 1
        rng = handler.headers.get("Range", "")
        m = re.match(r"bytes=(\d*)-(\d*)$", rng.strip())
        partial = False
        if m and size > 0:
            a, b = m.group(1), m.group(2)
            if a:
                start = int(a); end = int(b) if b else size - 1
            elif b:
                start = max(0, size - int(b))
            start = min(start, size - 1); end = min(end, size - 1)
            partial = True
        length = end - start + 1
        handler.send_response(206 if partial else 200)
        handler.send_header("Content-Type", ctype)
        handler.send_header("Accept-Ranges", "bytes")
        handler.send_header("Content-Length", str(length))
        handler.send_header("Cache-Control", "no-store")
        handler.send_header("Content-Disposition", f'inline; filename="{p.name}"')
        if partial:
            handler.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        handler.end_headers()
        try:
            with open(p, "rb") as f:
                f.seek(start)
                left = length
                while left > 0:
                    chunk = f.read(min(1 << 16, left))
                    if not chunk:
                        break
                    handler.wfile.write(chunk)
                    left -= len(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass


class Jobs:
    """Commands that outlive a turn. One registry file; one log per job."""

    def __init__(self, out_dir: Path, env_fn, wrap=None):
        self.dir = out_dir / "jobs"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.reg = self.dir / "jobs.json"
        self.env_fn = env_fn
        self.wrap = wrap or (lambda argv: argv)   # runs the job as another user when the bridge says so
        self.lock = threading.Lock()
        self.unseen: set[str] = set()

    def _load(self) -> list:
        try:
            return json.loads(self.reg.read_text())
        except Exception:
            return []

    def _save(self, items: list) -> None:
        self.reg.write_text(json.dumps(items, indent=1))

    def start(self, command: str, cwd: str | None, title: str = "") -> dict:
        command = (command or "").strip()
        if not command:
            return {"error": "empty command"}
        if re.search(r"(^|[\s;&|(])sudo(\s|$)", command):
            return {"error": "jobs never run sudo; ask for that in the chat so it gets a card"}
        wd = Path(cwd).expanduser() if cwd else None
        if wd is not None and not wd.is_dir():
            return {"error": f"no such folder: {wd}"}
        with self.lock:
            items = self._load()
            jid = f"J{int(time.time())}{len(items) + 1:03d}"
            log = self.dir / f"{jid}.log"
            lf = open(log, "ab")
            lf.write(f"# {jid} {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} in {wd or os.getcwd()}\n# {command}\n".encode())
            lf.flush()
            try:
                proc = subprocess.Popen(self.wrap(["bash", "-lc", command]), cwd=str(wd) if wd else None, env=self.env_fn(),
                                        stdout=lf, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
            except Exception as e:  # noqa: BLE001
                lf.close()
                return {"error": f"could not start: {type(e).__name__}"}
            rec = {"id": jid, "title": (title or command)[:120], "command": command[:1000], "cwd": str(wd) if wd else None,
                   "pid": proc.pid, "started": int(time.time()), "ended": None, "rc": None, "log": str(log)}
            items.append(rec)
            self._save(items)

        def _wait():
            rc = proc.wait()
            lf.close()
            with self.lock:
                cur = self._load()
                for r in cur:
                    if r["id"] == jid:
                        r["ended"] = int(time.time()); r["rc"] = rc
                self._save(cur)
                self.unseen.add(jid)
        threading.Thread(target=_wait, daemon=True).start()
        return rec

    def list(self, n: int = 30) -> list:
        items = self._load()
        return list(reversed(items))[:n]

    def get(self, jid: str, tail_bytes: int = 4000) -> dict | None:
        for r in self._load():
            if r["id"] == jid:
                out = dict(r)
                try:
                    data = Path(r["log"]).read_bytes()
                    out["tail"] = data[-tail_bytes:].decode("utf-8", "replace")
                    out["log_size"] = len(data)
                except OSError:
                    out["tail"] = ""
                out["running"] = r["ended"] is None
                return out
        return None

    def take_unseen(self) -> list:
        with self.lock:
            ids = list(self.unseen); self.unseen.clear()
        return [self.get(i, 600) for i in ids]


class Uploads:
    def __init__(self, in_dir: Path):
        self.dir = in_dir

    @staticmethod
    def _safe_name(name: str) -> str:
        name = os.path.basename(name or "file").strip() or "file"
        name = re.sub(r"[^A-Za-z0-9._ -]+", "_", name)[:120]
        return name

    def save_multipart(self, handler) -> dict:
        n = int(handler.headers.get("Content-Length") or 0)
        ctype = handler.headers.get("Content-Type", "")
        if n <= 0 or n > MAX_UPLOAD:
            return {"error": f"upload must be between 1 byte and {MAX_UPLOAD // (1024 * 1024)} MB"}
        if not ctype.startswith("multipart/form-data"):
            return {"error": "expected multipart/form-data"}
        raw = handler.rfile.read(n)
        msg = email.parser.BytesParser(policy=email.policy.HTTP).parsebytes(
            b"Content-Type: " + ctype.encode() + b"\r\nMIME-Version: 1.0\r\n\r\n" + raw)
        day = time.strftime("%Y-%m-%d", time.gmtime())
        dest_dir = self.dir / day
        dest_dir.mkdir(parents=True, exist_ok=True)
        saved = []
        for part in msg.iter_parts():
            fn = part.get_filename()
            if not fn:
                continue
            data = part.get_payload(decode=True) or b""
            name = self._safe_name(fn)
            dest = dest_dir / name
            i = 1
            while dest.exists():
                dest = dest_dir / f"{dest.stem}-{i}{dest.suffix}"; i += 1
            dest.write_bytes(data)
            saved.append({"name": dest.name, "path": str(dest), "size": len(data)})
        if not saved:
            return {"error": "no file in the upload"}
        return {"ok": True, "files": saved}

    def save_bytes(self, name: str, data: bytes) -> str:
        """One file from elsewhere (Telegram, 2026-09-29) into today's folder; returns its path."""
        day = time.strftime("%Y-%m-%d", time.gmtime())
        dest_dir = self.dir / day
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / self._safe_name(name)
        i = 1
        while dest.exists():
            dest = dest_dir / f"{dest.stem}-{i}{dest.suffix}"; i += 1
        dest.write_bytes(data)
        try:
            os.chmod(dest, 0o664)
        except OSError:
            pass
        return str(dest)


def shell_quote(cmd: list[str]) -> str:
    return " ".join(shlex.quote(c) for c in cmd)


class Telegram:
    """The bridge's own bot (2026-09-29): long polling, owner pinning, attachments, cards with
    buttons. Pure parts here, testable with a fake `api`; the bridge wires the turns."""

    LIMIT = 3900

    def __init__(self, token: str, state_file: Path, owner: str = "", api=None):
        self.token = token
        self.state_file = Path(state_file)
        self.forced_owner = str(owner or "").strip()
        self.api = api or self._http
        self._st: dict | None = None

    # -- http --
    def _http(self, method: str, _timeout: int, **params) -> dict:
        import urllib.request
        req = urllib.request.Request(f"https://api.telegram.org/bot{self.token}/{method}",
                                     data=json.dumps(params).encode(), method="POST",
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=_timeout) as r:
            return json.loads(r.read() or b"{}")

    def call(self, method: str, **params) -> dict:
        return self.api(method, 30, **params)

    def poll(self) -> list:
        """One long poll; advances the offset so an update is handled once."""
        st = self.state()
        r = self.api("getUpdates", 40, offset=st.get("offset", 0), timeout=30, allowed_updates=["message", "callback_query"])
        items = r.get("result") or []
        if items:
            self.save(offset=max(u.get("update_id", 0) for u in items) + 1)
        return items

    def download(self, file_id: str, name: str = "") -> tuple[bytes, str]:
        import urllib.request
        info = self.call("getFile", file_id=file_id)
        path = ((info.get("result") or {}).get("file_path") or "")
        if not path:
            raise RuntimeError("no file path")
        with urllib.request.urlopen(f"https://api.telegram.org/file/bot{self.token}/{path}", timeout=120) as r:
            data = r.read()
        return data, (name or Path(path).name)

    # -- state --
    def state(self) -> dict:
        if self._st is None:
            try:
                self._st = json.loads(self.state_file.read_text())
            except Exception:
                self._st = {}
        return self._st

    def save(self, **patch) -> None:
        st = self.state(); st.update(patch)
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(json.dumps(st))

    def owner(self):
        if self.forced_owner:
            try:
                return int(self.forced_owner)
            except ValueError:
                return self.forced_owner
        return self.state().get("owner")

    def owner_ok(self, chat_id) -> bool:
        o = self.owner()
        return o is not None and str(o) == str(chat_id)

    def pin(self, chat_id) -> None:
        self.save(owner=chat_id)

    # -- pure helpers --
    @staticmethod
    def chunks(text: str, n: int = LIMIT) -> list:
        text = text or ""
        out = []
        while len(text) > n:
            cut = text.rfind("\n", 0, n)
            if cut < n // 2:
                cut = text.rfind(" ", 0, n)
            if cut < n // 2:
                cut = n
            out.append(text[:cut]); text = text[cut:].lstrip("\n")
        out.append(text)
        return out

    @staticmethod
    def card_markup(pid: str) -> dict:
        return {"inline_keyboard": [[{"text": "Allow", "callback_data": f"allow:{pid}"},
                                     {"text": "Refuse", "callback_data": f"deny:{pid}"}]]}

    @staticmethod
    def parse_update(u: dict) -> dict | None:
        """What matters in an update: a message (text, voice, photo, document) or a button press."""
        cq = u.get("callback_query")
        if cq:
            msg = cq.get("message") or {}
            return {"kind": "callback", "chat_id": (msg.get("chat") or {}).get("id"), "message_id": msg.get("message_id"),
                    "callback_id": cq.get("id"), "data": cq.get("data") or ""}
        m = u.get("message") or u.get("edited_message")
        if not m:
            return None
        ev = {"kind": "message", "chat_id": (m.get("chat") or {}).get("id"), "message_id": m.get("message_id"),
              "text": (m.get("text") or m.get("caption") or "").strip(), "file_id": None, "file_name": None, "mime": None, "is_voice": False}
        if m.get("voice"):
            v = m["voice"]; ev.update(file_id=v.get("file_id"), file_name="voice.ogg", mime=v.get("mime_type") or "audio/ogg", is_voice=True)
        elif m.get("audio"):
            a = m["audio"]; ev.update(file_id=a.get("file_id"), file_name=a.get("file_name") or "audio.mp3", mime=a.get("mime_type"), is_voice=False)
        elif m.get("photo"):
            best = max(m["photo"], key=lambda p: p.get("file_size") or 0)
            ev.update(file_id=best.get("file_id"), file_name=f"photo-{m.get('message_id')}.jpg", mime="image/jpeg")
        elif m.get("document"):
            d = m["document"]; ev.update(file_id=d.get("file_id"), file_name=d.get("file_name") or "file", mime=d.get("mime_type"))
        elif m.get("video"):
            d = m["video"]; ev.update(file_id=d.get("file_id"), file_name=d.get("file_name") or f"video-{m.get('message_id')}.mp4", mime=d.get("mime_type"))
        return ev


def usage_summary(lines, now: float | None = None, titles: dict | None = None) -> dict:
    """Cost and usage (2026-09-29) from the turn audit: one dict per turn with ts, tok_in, tok_cached,
    tok_out, cost, thread, via, ms. Totals for today, the last 7 days, this month and all time;
    the top threads this month; page against telegram. Cost is a sum where the CLI reported one
    (an API key); on a subscription it stays None and the tokens are the measure."""
    import datetime as _dt
    now = now or time.time()
    today = time.strftime("%Y-%m-%d", time.gmtime(now))
    month = today[:7]
    week_from = time.strftime("%Y-%m-%d", time.gmtime(now - 7 * 86400))
    def blank():
        return {"turns": 0, "in": 0, "cached": 0, "out": 0, "cost": None, "ms": 0, "errors": 0}
    def add(b, e):
        b["turns"] += 1
        b["in"] += int(e.get("tok_in") or 0); b["cached"] += int(e.get("tok_cached") or 0); b["out"] += int(e.get("tok_out") or 0)
        b["ms"] += int(e.get("ms") or 0); b["errors"] += 1 if e.get("error") else 0
        c = e.get("cost")
        if isinstance(c, (int, float)):
            b["cost"] = (b["cost"] or 0.0) + float(c)
    out = {"today": blank(), "week": blank(), "month": blank(), "all": blank(), "threads": {}, "via": {}, "days": {}}
    for raw in lines:
        try:
            e = json.loads(raw) if isinstance(raw, str) else raw
        except Exception:
            continue
        day = str(e.get("ts") or "")[:10]
        if not day:
            continue
        add(out["all"], e)
        if day == today:
            add(out["today"], e)
        if day >= week_from:
            add(out["week"], e)
        if day[:7] == month:
            add(out["month"], e)
            th = e.get("brain_session") or e.get("thread") or "?"
            out["threads"].setdefault(th, blank()); add(out["threads"][th], e)
            v = e.get("via") or "page"
            out["via"].setdefault(v, blank()); add(out["via"][v], e)
            out["days"].setdefault(day, blank()); add(out["days"][day], e)
    top = sorted(out["threads"].items(), key=lambda kv: -(kv[1]["in"] + kv[1]["out"]))[:6]
    out["threads"] = [{"thread": k, "title": (titles or {}).get(k), **v} for k, v in top]
    out["days"] = [{"day": k, **v} for k, v in sorted(out["days"].items())][-31:]
    out["cost_note"] = ("USD as the reasoner reported it" if out["all"]["cost"] is not None
                        else "no cost figures: a subscription sign-in reports none; tokens are the measure")
    return out
