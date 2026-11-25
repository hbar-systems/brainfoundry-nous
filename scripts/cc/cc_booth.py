"""The booth: just sing (SING-FREE-1, 2026-11-24). The bridge side of the console's /sing page.

hbar 2026-11-24: "I don't want a loop. I just wanted to sing." The page records the microphone as plain PCM and
sends one WAV per take; this module keeps it in one folder (CC_BOOTH_DIR, default <out>/studio/booth), one
sub-folder per day:

  <root>/<YYYY-MM-DD>/<YYYY-MM-DD>_<HHMMSS>_<name>.wav    the take, exactly the bytes the page sent, never rewritten
  <root>/<YYYY-MM-DD>/<YYYY-MM-DD>_<HHMMSS>_<name>.json   its card (hbar.booth.take/v1): name, made, seconds, format,
                                                          sha256 of the wav, what it was sung over (a track, a loop)

Doors (behind the bridge's page gate like every page route: the console's operator token, no app frames):
  GET  /cc/booth                  {ok, dir, takes: [...]} newest first (at most 200)
  GET  /cc/booth/file?path=<p>    a take's wav (byte ranges honoured)
  POST /cc/booth/take             body = the wav (audio/wav), header X-Booth-Meta = urlencoded JSON
                                  {name?, over?}; answers the take's card
  POST /cc/booth/name {file, name}  names the take afterwards: the wav and its card are renamed side by side,
                                  the wav's bytes stay as they were (its sha256 is checked before and after)

A name is said or typed after the take; until then it is "take". Nothing is ever overwritten: a taken name gets
-1, -2 ... Only .wav and .json in the day folders are reached; no dot names, nothing through a symlink out.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import struct
import threading
import time
from pathlib import Path
from urllib.parse import unquote

import cc_extras

MAX_TAKE = 300 * 1024 * 1024          # 300 MB: about 36 min of 48 kHz 24-bit mono
META_MAX = 4096
LIST_MAX = 200
DIALECT = "hbar.booth.take/v1"
_DAY = re.compile(r"\d{4}-\d{2}-\d{2}")
_FILE = re.compile(r"(\d{4}-\d{2}-\d{2})_(\d{6})_([a-z0-9][a-z0-9-]{0,59})\.wav")


_RU = dict(zip("абвгдеёжзийклмнопрстуфхцчшщъыьэюя",
               ["a", "b", "v", "g", "d", "e", "e", "zh", "z", "i", "y", "k", "l", "m", "n", "o", "p", "r", "s", "t",
                "u", "f", "kh", "ts", "ch", "sh", "shch", "", "y", "", "e", "yu", "ya"]))


def slug(name) -> str:
    """A said name as a file name part: lower case, letters and digits joined by dashes, 60 at most; Cyrillic
    is spelled in Latin letters (the card keeps the name as said)."""
    s = "".join(_RU.get(c, c) for c in str(name or "").strip().lower())
    s = re.sub(r"[^\w]+", "-", s, flags=re.ASCII).strip("-_").replace("_", "-")
    s = re.sub(r"-{2,}", "-", s)[:60].strip("-")
    return s or "take"


def wav_info(data: bytes) -> dict | None:
    """channels, rate, bits and seconds of a PCM or float WAV, or None when it is not one."""
    if len(data) < 44 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        return None
    i, fmt, size = 12, None, None
    while i + 8 <= len(data):
        cid, n = data[i:i + 4], struct.unpack("<I", data[i + 4:i + 8])[0]
        if cid == b"fmt " and n >= 16:
            tag, ch, rate, _, align, bits = struct.unpack("<HHIIHH", data[i + 8:i + 24])
            fmt = {"format": tag, "channels": ch, "rate": rate, "bits": bits, "align": align}
        elif cid == b"data":
            size = min(n, len(data) - i - 8)
            break
        i += 8 + n + (n & 1)
    if not fmt or size is None or fmt["format"] not in (1, 3, 0xFFFE) or not fmt["rate"] or not fmt["align"]:
        return None
    if not (1 <= fmt["channels"] <= 8 and 8000 <= fmt["rate"] <= 192000 and fmt["bits"] in (16, 24, 32)):
        return None
    return {"channels": fmt["channels"], "rate": fmt["rate"], "bits": fmt["bits"],
            "seconds": round(size / fmt["align"] / fmt["rate"], 3)}


def _sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def _clean_over(over) -> dict | None:
    """What the take was sung over, as the page said it: kept small and plain."""
    if not isinstance(over, dict):
        return None
    out = {}
    for k, v in over.items():
        if not isinstance(k, str) or len(k) > 40:
            continue
        if isinstance(v, (int, float, bool)) or v is None:
            out[k] = v
        elif isinstance(v, str):
            out[k] = v[:300]
        elif isinstance(v, dict):
            out[k] = {str(a)[:40]: (b if isinstance(b, (int, float, bool)) or b is None else str(b)[:300])
                      for a, b in list(v.items())[:30]}
        elif isinstance(v, list):
            # a short list of number pairs (DEMO-1: the embed's clock against the take's, [take_s, video_s])
            pairs = [[float(x[0]), float(x[1])] for x in v[:64] if isinstance(x, (list, tuple)) and len(x) == 2
                     and all(isinstance(y, (int, float)) and not isinstance(y, bool) and math.isfinite(y) for y in x)]
            if pairs:
                out[k] = pairs
        if len(out) >= 30:
            break
    return out or None


class Booth:
    def __init__(self, root):
        self.root = Path(root)
        self.lock = threading.Lock()

    # ---- where things are
    def _real_root(self, create: bool = False) -> Path | None:
        if create and not self.root.exists():
            try:
                os.makedirs(self.root, mode=0o2775, exist_ok=True)
            except OSError:
                return None
        try:
            r = self.root.resolve(strict=True)
        except OSError:
            return None
        return r if r.is_dir() else None

    def take_path(self, raw) -> Path | None:
        """A take's wav by its absolute path or its file name; None unless it is a take in a day folder."""
        r = self._real_root()
        s = str(raw or "").strip()
        if r is None or not s or "\x00" in s:
            return None
        name = Path(s).name
        m = _FILE.fullmatch(name)
        if not m:
            return None
        p = r / m.group(1) / name
        if Path(s).is_absolute():
            try:
                if Path(s).resolve() != p.resolve():
                    return None
            except (OSError, RuntimeError):
                return None
        try:
            q = p.resolve(strict=True)
            q.relative_to(r)
        except (OSError, ValueError, RuntimeError):
            return None
        return q if q.is_file() else None

    # ---- the doors
    def state(self) -> dict:
        r = self._real_root()
        if r is None:
            return {"ok": True, "dir": str(self.root), "takes": []}
        takes = []
        for day in sorted((d for d in r.iterdir() if d.is_dir() and _DAY.fullmatch(d.name)), reverse=True):
            for w in sorted(day.glob("*.wav"), reverse=True):
                if _FILE.fullmatch(w.name):
                    takes.append(self._card(w))
                if len(takes) >= LIST_MAX:
                    break
            if len(takes) >= LIST_MAX:
                break
        return {"ok": True, "dir": str(r), "takes": takes}

    def _card(self, w: Path) -> dict:
        try:
            c = json.loads(w.with_suffix(".json").read_text())
            if not isinstance(c, dict):
                c = {}
        except (OSError, ValueError):
            c = {}
        m = _FILE.fullmatch(w.name)
        st = w.stat()
        c.update({"file": w.name, "path": str(w), "size": st.st_size, "day": m.group(1),
                  "name": c.get("name") or m.group(3)})
        return c

    def save(self, handler) -> tuple[int, dict]:
        try:
            meta = json.loads(unquote(handler.headers.get("X-Booth-Meta", "") or "{}")[:META_MAX] or "{}")
        except ValueError:
            meta = {}
        if not isinstance(meta, dict):
            meta = {}
        data = cc_extras.read_body(handler, MAX_TAKE)
        if not data:
            return 413, {"ok": False, "error": f"a take must be between 1 byte and {MAX_TAKE // (1024 * 1024)} MB"}
        info = wav_info(data)
        if info is None:
            return 400, {"ok": False, "error": "that is not a WAV the booth keeps (PCM 16/24/32-bit or float)"}
        r = self._real_root(create=True)
        if r is None:
            return 500, {"ok": False, "error": f"the booth folder {self.root} cannot be made"}
        now = time.time()
        day = time.strftime("%Y-%m-%d", time.localtime(now))
        hms = time.strftime("%H%M%S", time.localtime(now))
        name = slug(meta.get("name"))
        card = {"dialect": DIALECT, "name": name, "title": str(meta.get("name") or "").strip()[:120] or None, "made": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(now)),
                **info, "sha256": hashlib.sha256(data).hexdigest(), "over": _clean_over(meta.get("over")),
                "page": _clean_over(meta.get("page"))}
        with self.lock:
            try:
                dfd = cc_extras.open_dir(r / day, create=True, mode=0o2775)
            except (OSError, cc_extras.UnsafePath) as e:
                return 500, {"ok": False, "error": f"could not open today's booth folder: {e}"}
            try:
                stem = f"{day}_{hms}_{name}"
                cand, i = stem, 1
                while True:
                    try:
                        fd = cc_extras.create_new(dfd, cand + ".wav", 0o664)
                        break
                    except FileExistsError:
                        cand = f"{stem}-{i}"; i += 1
                        if i > 1000:
                            return 409, {"ok": False, "error": "too many takes with that name this second"}
                with os.fdopen(fd, "wb") as f:
                    f.write(data)
                cc_extras.replace_file(dfd, cand + ".json", (json.dumps(card, indent=1) + "\n").encode(), 0o664)
            finally:
                os.close(dfd)
        w = r / day / (cand + ".wav")
        print(f"booth: kept {w} ({info['seconds']} s)", flush=True)
        return 200, {"ok": True, "take": self._card(w)}

    def rename(self, file, name) -> tuple[int, dict]:
        w = self.take_path(file)
        if w is None:
            return 404, {"ok": False, "error": "no such take in the booth"}
        m = _FILE.fullmatch(w.name)
        new = slug(name)
        if new == m.group(3):
            return 200, {"ok": True, "take": self._card(w)}
        with self.lock:
            before = _sha(w)
            side = w.with_suffix(".json")
            stem, i = f"{m.group(1)}_{m.group(2)}_{new}", 1
            cand = stem
            while (w.parent / (cand + ".wav")).exists() or (w.parent / (cand + ".json")).exists():
                cand = f"{stem}-{i}"[:80]; i += 1
                if i > 1000:
                    return 409, {"ok": False, "error": "that name is taken"}
            nw = w.parent / (cand + ".wav")
            try:
                os.link(w, nw)          # never over an existing file: link fails if the name appeared meanwhile
                os.unlink(w)
            except OSError as e:
                return 409, {"ok": False, "error": f"could not rename: {e.strerror or e}"}
            try:
                c = json.loads(side.read_text()) if side.is_file() else {}
            except (OSError, ValueError):
                c = {}
            if not isinstance(c, dict):
                c = {}
            c.update({"name": new, "title": str(name or "").strip()[:120] or None, "named": time.strftime("%Y-%m-%dT%H:%M:%S%z")})
            c.setdefault("sha256", before)
            if _sha(nw) != c["sha256"]:
                return 500, {"ok": False, "error": "the take's bytes do not match its card; nothing more done"}
            dfd = cc_extras.open_dir(w.parent)
            try:
                cc_extras.replace_file(dfd, cand + ".json", (json.dumps(c, indent=1) + "\n").encode(), 0o664)
            finally:
                os.close(dfd)
            if side.is_file() and side.name != cand + ".json":
                side.unlink()
        return 200, {"ok": True, "take": self._card(nw)}

    def serve(self, handler, raw) -> None:
        p = self.take_path(raw)
        if p is None:
            body = b'{"error": "no such take in the booth"}'
            handler.send_response(404)
            handler.send_header("Content-Type", "application/json")
            handler.send_header("Content-Length", str(len(body)))
            handler.send_header("Cache-Control", "no-store")
            handler.end_headers()
            handler.wfile.write(body)
            return
        cc_extras.Files({"booth": str(self._real_root())}).serve(handler, str(p))
