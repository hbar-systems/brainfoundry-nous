"""The memo tape as a console page (TAPE-2, 2026-11-14). The bridge side: one folder, read and written only
through these doors.

A brain may keep a memo tape: a folder (CC_TAPE_DIR, default <in>/memos) that a watcher fills with memos cut
into bits, one <id>/bits.json each, an index.json listing them, a board.json across them and, if the watcher
puts it there, a vocab.json with the words a ruling may use. The console's /tape page reads and writes that
folder through the bridge's /cc/tape routes and nowhere else:

  GET  /cc/tape                       {tape: bool, dir, vocab, signer}; tape is false when there is no index.json
  GET  /cc/tape/file?path=<p>         a file in the folder (json, text, audio, video), byte ranges honoured
  GET  /cc/tape/stat?path=<p>         {ok, mtime, size} of a file in the folder
  POST /cc/tape/write {path, text, mtime?}   only the files the page itself makes (see WRITABLE)

<p> is absolute (inside the folder) or relative to it. Nothing outside the folder resolves, symlinks are followed
before the check, and no name that starts with a dot is reached. These routes sit behind the bridge's page gate
like every other page route: the operator token the console's proxy adds after its login, and the refusal of
app frames and other sites (Origin "null", Sec-Fetch-Site cross-site). A brain without a tape answers
{tape: false} and the page shows nothing.

Recording (talk-through) uses the console's own /cc/upload for the slices (they land in <in>/<date>/ as
talk-<id>-NNNN.<ext>.part) and /cc/tape/write for inbox/talk-<id>.rec.json, the list of slices so far; the
watcher stitches the slices when the list says done.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import cc_extras

READ_EXT = {".json", ".md", ".txt", ".webm", ".m4a", ".mp4", ".mp3", ".ogg", ".oga", ".opus", ".wav", ".aac",
            ".flac", ".caf", ".aif", ".aiff", ".mov", ".mkv"}
_NAME = r"[A-Za-z0-9][A-Za-z0-9._ -]{0,160}"
_ID = r"[A-Za-z0-9][A-Za-z0-9._-]{0,120}"
# relative path -> the page may write it. Everything else in the folder is the watcher's.
WRITABLE = [
    re.compile(rf"{_ID}/bits\.json"),                       # a memo's bits: rulings, sign-off, re-cuts
    re.compile(rf"{_ID}/dispatch/bit-\d{{2,3}}\.reply-\d{{1,3}}\.md"),   # a reply to a job a bit became
    re.compile(rf"inbox/{_NAME}\.take\.txt"),               # marker: take this uploaded file as a memo
    re.compile(rf"inbox/text-\d{{6,12}}\.txt"),             # a typed thought
    re.compile(r"inbox/talk-[A-Za-z0-9_-]{1,40}\.rec\.json"),  # a talk-through take: its slices so far
]
WRITE_MAX = cc_extras.Files.WRITE_MAX


class Tape:
    def __init__(self, root, signer: str = "owner"):
        self.root = Path(root)
        self.signer = (signer or "owner").strip()[:40] or "owner"

    def _real_root(self) -> Path | None:
        try:
            r = self.root.resolve(strict=True)
        except OSError:
            return None
        return r if r.is_dir() else None

    def present(self) -> bool:
        r = self._real_root()
        return r is not None and (r / "index.json").is_file()

    def state(self) -> dict:
        if not self.present():
            return {"tape": False}
        r = self._real_root()
        return {"tape": True, "dir": str(r), "vocab": (r / "vocab.json").is_file(), "signer": self.signer}

    def rel(self, raw) -> str | None:
        """The path relative to the folder, or None when it is not in it (or reaches a dot name)."""
        r = self._real_root()
        s = str(raw or "").strip()
        if r is None or not s or "\x00" in s:
            return None
        p = Path(s)
        if not p.is_absolute():
            p = r / p
        try:
            # the configured spelling of the folder counts as the folder (a symlinked in/, a trailing slash)
            if self.root.is_absolute():
                try:
                    p = r / p.relative_to(self.root)
                except ValueError:
                    pass
            q = p.resolve()
            rel = q.relative_to(r)
        except (OSError, ValueError, RuntimeError):
            return None
        parts = rel.parts
        if not parts or any(x.startswith(".") for x in parts):
            return None
        return rel.as_posix()

    def path(self, raw) -> Path | None:
        rel = self.rel(raw)
        return None if rel is None else self._real_root() / rel

    def readable(self, raw) -> tuple[Path | None, str]:
        p = self.path(raw)
        if p is None:
            return None, "not on the tape"
        if p.suffix.lower() not in READ_EXT:
            return None, "not a file the tape shows"
        if not p.is_file():
            return None, "no such file on the tape"
        return p, ""

    def stat(self, raw) -> dict:
        p, why = self.readable(raw)
        if p is None:
            return {"ok": False, "error": why}
        st = p.stat()
        return {"ok": True, "mtime": int(st.st_mtime), "size": st.st_size}

    def serve(self, handler, raw) -> None:
        p, why = self.readable(raw)
        if p is None:
            import json
            body = json.dumps({"error": why}).encode()
            handler.send_response(404)
            handler.send_header("Content-Type", "application/json")
            handler.send_header("Content-Length", str(len(body)))
            handler.send_header("Cache-Control", "no-store")
            handler.end_headers()
            handler.wfile.write(body)
            return
        cc_extras.Files({"tape": str(self._real_root())}).serve(handler, str(p))

    def writable(self, raw) -> tuple[Path | None, str]:
        if not self.present():
            return None, "there is no memo tape on this brain"
        rel = self.rel(raw)
        if rel is None:
            return None, "not on the tape"
        if not any(rx.fullmatch(rel) for rx in WRITABLE):
            return None, "the page does not write that file"
        p = self._real_root() / rel
        if p.exists() and not p.is_file():
            return None, "that is a folder"
        return p, ""

    def write(self, raw, text, expect_mtime=None) -> dict:
        p, why = self.writable(raw)
        if p is None:
            return {"ok": False, "error": why}
        if not isinstance(text, str):
            return {"ok": False, "error": "text is needed"}
        data = text.encode("utf-8")
        if len(data) > WRITE_MAX:
            return {"ok": False, "error": "too large to save from here"}
        if expect_mtime is not None and p.exists() and int(p.stat().st_mtime) != int(expect_mtime):
            return {"ok": False, "error": "changed on disk since you opened it; reload, then edit again",
                    "conflict": True, "mtime": int(p.stat().st_mtime)}
        if not p.parent.is_dir():
            if p.parent.name == "inbox" and p.parent.parent == self._real_root():
                os.makedirs(p.parent, mode=0o2775, exist_ok=True)
            else:
                return {"ok": False, "error": "the folder does not exist"}
        try:
            dfd = cc_extras.open_dir(p.parent)
            try:
                cc_extras.replace_file(dfd, p.name, data, 0o664)
            finally:
                os.close(dfd)
        except OSError as e:
            return {"ok": False, "error": f"could not save: {e.strerror or e}"}
        st = p.stat()
        return {"ok": True, "path": str(p), "size": st.st_size, "mtime": int(st.st_mtime)}
