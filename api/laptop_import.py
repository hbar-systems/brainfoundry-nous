"""The laptop on-ramp, brain side (2026-11-03, docs/IMPORT.md section "From your laptop").

The person runs scripts/import/brain_import.py on their own computer. It asks folder by
folder what to bring and sends only the files they said yes to. The brain never reaches
into the laptop; it only receives.

This module holds the one-time import tokens. The owner mints one from the console
(owner key); the helper carries only that token, never the owner key. A token:
- is stored as its sha256, never in clear;
- lives at most TTL seconds (default 2 hours) and closes when the helper says finish;
- carries a file and byte cap for the run;
- is the only open one: minting a new token closes every earlier one.
It lets its holder do exactly one thing: propose files into Knowledge. Every file
becomes a PENDING proposal; nothing is remembered before the owner approves it.

Audio (2026-11-03, M7-G) is not Knowledge: chosen audio files are kept as files in the
member's ~/in/<date>/import/ (LAPTOP_AUDIO_DIR, a bind mount of the hands' ~/in), listed in
audio.tsv beside them for the music tools. They are never proposed to memory.
"""
import hashlib
import json
import os
import re
import secrets
import threading
import time
from pathlib import Path, PurePosixPath

TTL_SECONDS = 2 * 3600
MAX_FILES = 2000
MAX_BYTES = 2 * 1024 ** 3
MAX_FILE_BYTES = 25 * 1024 ** 2

# What Knowledge can read: text and code decode as UTF-8, PDF and DOCX through the
# upload extractors, images through OCR (sent only when the person names the type).
TEXT_EXT = {
    "txt", "md", "markdown", "rst", "org", "tex", "csv", "tsv", "json", "yaml", "yml",
    "toml", "xml", "html", "htm", "srt", "vtt", "log",
    "py", "js", "ts", "tsx", "jsx", "sh", "c", "h", "cpp", "rs", "go", "java", "rb", "swift",
    "kt", "m", "r", "jl", "sql", "ipynb",
}
DOC_EXT = {"pdf", "docx"}
IMAGE_EXT = {"png", "jpg", "jpeg", "gif", "webp", "tif", "tiff", "bmp"}
ACCEPTED_EXT = TEXT_EXT | DOC_EXT | IMAGE_EXT
# Kept as files for the music tools, not read: audio, MIDI and Ableton sets.
AUDIO_EXT = {"wav", "aif", "aiff", "mp3", "flac", "m4a", "ogg", "als", "mid", "midi"}
MAX_AUDIO_FILE_BYTES = 200 * 1024 ** 2
ARRIVALS_KEPT = 500

TOKEN_RE = re.compile(r"^imp_[A-Za-z0-9_-]{32,64}$")


class TokenError(Exception):
    """Refused: 401 for a bad or closed token, 413 for a cap."""

    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class TokenStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._lock = threading.Lock()

    def _load(self) -> dict:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, ValueError):
            return {}

    def _save(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
        os.chmod(tmp, 0o600)
        os.replace(tmp, self.path)

    def mint(self, ttl: int = TTL_SECONDS, max_files: int = MAX_FILES, max_bytes: int = MAX_BYTES) -> dict:
        raw = "imp_" + secrets.token_urlsafe(32)
        now = time.time()
        with self._lock:
            data = self._load()
            for rec in data.values():  # one open token at a time
                rec["closed"] = rec.get("closed") or now
            # forget records older than a day
            data = {h: r for h, r in data.items() if now - r.get("created", 0) < 86400}
            data[_hash(raw)] = {"created": now, "expires": now + ttl, "closed": None,
                                "files": 0, "bytes": 0, "max_files": max_files, "max_bytes": max_bytes}
            self._save(data)
        return {"token": raw, "expires_at": int(now + ttl), "max_files": max_files,
                "max_bytes": max_bytes, "max_file_bytes": MAX_FILE_BYTES}

    def _get(self, data: dict, raw: str) -> dict:
        if not raw or not TOKEN_RE.match(raw):
            raise TokenError(401, "import token missing or malformed")
        rec = data.get(_hash(raw))
        if rec is None:
            raise TokenError(401, "unknown import token")
        if rec.get("closed"):
            raise TokenError(401, "import token already used up (finished or replaced)")
        if time.time() > rec["expires"]:
            raise TokenError(401, "import token expired; mint a new one in the console")
        return rec

    def check(self, raw: str) -> dict:
        with self._lock:
            return dict(self._get(self._load(), raw))

    def charge(self, raw: str, size: int, ext: str = "") -> dict:
        """Count one file against the run's caps, before it is proposed or kept."""
        cap = max_file_bytes(ext)
        if size > cap:
            raise TokenError(413, f"file over {cap // 1024 ** 2} MB")
        with self._lock:
            data = self._load()
            rec = self._get(data, raw)
            if rec["files"] + 1 > rec["max_files"]:
                raise TokenError(413, f"file cap of this run reached ({rec['max_files']})")
            if rec["bytes"] + size > rec["max_bytes"]:
                raise TokenError(413, "byte cap of this run reached")
            rec["files"] += 1
            rec["bytes"] += size
            self._save(data)
            return dict(rec)

    def note(self, raw: str, entry: dict) -> None:
        """One line of what arrived, for the console card's live list (newest last, capped)."""
        with self._lock:
            data = self._load()
            rec = data.get(_hash(raw or ""))
            if rec is None:
                return
            arrived = rec.setdefault("arrived", [])
            arrived.append(dict(entry, at=int(time.time())))
            del arrived[:-ARRIVALS_KEPT]
            self._save(data)

    def latest(self) -> dict | None:
        """The newest run, for the console: open or not, counts, and what arrived. No token."""
        with self._lock:
            data = self._load()
        if not data:
            return None
        rec = max(data.values(), key=lambda r: r.get("created", 0))
        now = time.time()
        return {"created": int(rec["created"]), "expires_at": int(rec["expires"]),
                "open": not rec.get("closed") and now <= rec["expires"],
                "files": rec["files"], "bytes": rec["bytes"], "arrived": rec.get("arrived", [])}

    def close(self, raw: str) -> dict:
        with self._lock:
            data = self._load()
            rec = self._get(data, raw)
            rec["closed"] = time.time()
            self._save(data)
            return dict(rec)


def bearer(authorization: str) -> str:
    if authorization and authorization.startswith("Bearer "):
        return authorization[len("Bearer "):].strip()
    return ""


def clean_relpath(path: str) -> str:
    """The laptop-side path as the document name: forward slashes, no root, no '..',
    no hidden parts. Raises ValueError otherwise."""
    p = (path or "").replace("\\", "/").strip()
    if not p or p.startswith("/") or re.match(r"^[A-Za-z]:", p):
        raise ValueError("path must be relative")
    parts = PurePosixPath(p).parts
    if any(x in ("..", ".") or x.startswith(".") for x in parts):
        raise ValueError("path may not hold '..' or hidden parts")
    if len(p) > 400:
        raise ValueError("path too long")
    return "/".join(parts)


def extension(path: str) -> str:
    name = path.rsplit("/", 1)[-1]
    return name.rsplit(".", 1)[-1].lower() if "." in name else ""


def decode_text(content: bytes) -> str:
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        return content.decode("latin-1")


def max_file_bytes(ext: str) -> int:
    return MAX_AUDIO_FILE_BYTES if ext in AUDIO_EXT else MAX_FILE_BYTES


def _chown_like(path: Path, root: Path) -> None:
    """The api runs as root in its container; files it writes into a member's ~/in take
    the owner of that folder, so the member's hands can read and move them."""
    try:
        st = root.stat()
        if os.geteuid() == 0 and (st.st_uid, st.st_gid) != (0, 0):
            os.chown(path, st.st_uid, st.st_gid)
    except OSError:
        pass


def audio_dest(root: Path, rel: str, created: float) -> Path:
    """Where one audio file lands: <root>/<date of the run>/import/<laptop path>; a name
    already taken gets ' (2)', ' (3)', ... (nothing is overwritten)."""
    day = time.strftime("%Y-%m-%d", time.gmtime(created))
    dest = Path(root) / day / "import" / rel
    if not dest.exists():
        return dest
    stem, suf = dest.stem, dest.suffix
    for i in range(2, 1000):
        cand = dest.with_name(f"{stem} ({i}){suf}")
        if not cand.exists():
            return cand
    raise ValueError("too many files of that name")


def keep_audio(root: Path, dest: Path, tmp: Path, size: int, sha: str) -> str:
    """Move a fully received file into place, open it to the member, list it in audio.tsv.
    Returns the path as the member sees it under ~/in."""
    root = Path(root)
    made = []
    d = dest.parent
    while d != root and not d.exists():
        made.append(d)
        d = d.parent
    dest.parent.mkdir(parents=True, exist_ok=True)
    for d in reversed(made):
        os.chmod(d, 0o755)
        _chown_like(d, root)
    os.replace(tmp, dest)
    os.chmod(dest, 0o644)
    _chown_like(dest, root)
    import_dir = dest.relative_to(root).parts[:2]  # (<date>, "import")
    index = root.joinpath(*import_dir) / "audio.tsv"
    fresh = not index.exists()
    with open(index, "a", encoding="utf-8") as f:
        if fresh:
            f.write("file\tbytes\tsha256\tarrived\n")
        f.write(f"{dest.relative_to(index.parent).as_posix()}\t{size}\t{sha}\t"
                f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}\n")
    if fresh:
        os.chmod(index, 0o644)
        _chown_like(index, root)
    return "in/" + dest.relative_to(root).as_posix()
