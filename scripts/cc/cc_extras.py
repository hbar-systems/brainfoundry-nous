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
TEXT_SUFFIXES = {".md", ".txt", ".json", ".py", ".js", ".ts", ".sh", ".yml", ".yaml", ".toml", ".csv", ".tsv", ".log", ".html", ".css", ".ini", ".cfg"}
KIND_BY_SUFFIX = {
    **{s: "audio" for s in (".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aiff", ".aif")},
    **{s: "video" for s in (".mp4", ".webm", ".mov", ".m4v")},
    **{s: "image" for s in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg")},
    ".pdf": "pdf",
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

    def __init__(self, out_dir: Path, env_fn):
        self.dir = out_dir / "jobs"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.reg = self.dir / "jobs.json"
        self.env_fn = env_fn
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
                proc = subprocess.Popen(["bash", "-lc", command], cwd=str(wd) if wd else None, env=self.env_fn(),
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


def shell_quote(cmd: list[str]) -> str:
    return " ".join(shlex.quote(c) for c in cmd)
