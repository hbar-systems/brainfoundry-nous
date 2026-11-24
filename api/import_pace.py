"""Moving in at the pace a brain can take (IMPORT-PACE-1, hbar 2026-11-24, docs/IMPORT.md "Pace").

hbar, after two days of one member's sitting: "did we consider limits so we dont import from computer more
than what brain can handle? notice how long the onboarding takes." Measured in that sitting: 1,865 files
chosen, 1,825 arrived, 40 refused, the health check silent for 15 s, three different counts on the home.

This module holds the pure rules; api/main.py wires them:
1. The reading cost of one file, from the rates measured on 2 cores (MEASURED below; the measure script and
   its numbers are in docs/IMPORT.md). Reading = extract + chunk + embed; embedding is nearly all of it.
2. Two passes. The first pass is what makes the brain useful today, inside FIRST_PASS_SECONDS of reading:
   folders the person named, then recent files, small documents before books. The rest is read in the
   background by the approve-all worker, slower, with a pause between documents and behind any chat.
3. One true count of what waits (documents and chats apart), for the card, the button and the footer.
4. Refusals by reason (too big, type, brain busy, other), so the agent lists them and retries only the
   retryable ones; a busy brain answers 503 "wait" with Retry-After, never a refusal.
"""
from __future__ import annotations

import threading
import time
from pathlib import PurePosixPath

# ── 1. measured reading rates (2026-11-24, docs/IMPORT.md "Pace": 2 cores of a Neoverse-N1, the core of the
# Hetzner CAX boxes; bge-large-en-v1.5 fp32 through ONNX Runtime with 2 threads as the stand-in for the
# container's torch, batch 32, 512 tokens; CHUNKER=words; synthetic files) ──
MEASURED = {
    "note_seconds": 12.5,              # a 400-word note, one chunk (10 notes: 12.46 to 12.86 s)
    "deck_seconds": 63.8,              # a 25-slide deck PDF, 1,550 words, 4 chunks (3 decks: 63.3 to 64.3 s)
    "seconds_per_chunk": 15.9,         # in a batch (padded to 512 tokens); a lone short chunk is 12.5
    "extract_book_seconds": 1.4,       # a 300-page PDF, text layer: pymupdf alone (latency.json: 10 reads 14.3 s)
    "health_on_loop_worst": 13.9,      # /health while 10 such reads ran on the event loop (the old route)
    "health_off_loop_worst": 0.085,    # the same reads in a worker thread (this change)
}
SECONDS_PER_CHUNK = MEASURED["seconds_per_chunk"]
WORDS_PER_CHUNK = 450                  # the word chunker's stride (api/chunker.py, CHUNKER=words)
FIXED_SECONDS = 0.15                   # per document: proposal, database rows, audit
OCR_SECONDS = 4.0                      # one picture read by OCR (estimate: tesseract, one page at 2 cores)
# Words in a file by its size: estimates per type, conservative (more words than usual), so the time said
# on the home is an upper bound more often than not. Plain text: about 6 bytes a word. PDF and DOCX carry
# fonts and pictures: a 300-page book of 100k words is 2 to 10 MB; 40 bytes a word is its dense end.
BYTES_PER_WORD = {"text": 6, "docx": 25, "pdf": 40}
MAX_WORDS = 300_000

FIRST_PASS_SECONDS = 15 * 60
# A book: a long PDF or DOCX, read overnight unless the person says "now".
BIG_BYTES = 5 * 1024 ** 2
RECENT_SECONDS = 180 * 86400

# ── 2. the background pace (the approve-all worker) ──
PACE_SECONDS = 0.5                     # pause between two documents of the second pass
CHAT_QUIET_SECONDS = 8                 # the worker waits while a chat ran within this long
CHAT_WAIT_MAX = 120                    # ... but never longer than this per document
# ── upload reading on the request path: at most this many files extracted at once; beyond, "wait" ──
UPLOAD_READERS = 1
UPLOAD_QUEUE = 2
RETRY_AFTER_SECONDS = 5


def _ext(rel: str) -> str:
    base = PurePosixPath(rel).name.lower()
    return base.rsplit(".", 1)[1] if "." in base else ""


def file_kind(rel: str) -> str:
    e = _ext(rel)
    if e == "pdf":
        return "pdf"
    if e == "docx":
        return "docx"
    if e in {"png", "jpg", "jpeg", "gif", "webp", "tif", "tiff", "bmp"}:
        return "image"
    return "text"


def is_big(rel: str, size: int) -> bool:
    return file_kind(rel) in ("pdf", "docx") and size >= BIG_BYTES


def read_seconds(rel: str, size: int) -> float:
    """Seconds of reading for one file on a 2-core brain, from the measured rate per chunk."""
    k = file_kind(rel)
    if k == "image":
        return FIXED_SECONDS + OCR_SECONDS + SECONDS_PER_CHUNK
    words = min(MAX_WORDS, max(1, size // BYTES_PER_WORD["text" if k == "text" else k]))
    chunks = max(1, -(-words // WORDS_PER_CHUNK))
    return FIXED_SECONDS + chunks * SECONDS_PER_CHUNK


def first_pass(rows, now: float | None = None, budget: float = FIRST_PASS_SECONDS, named=(), big_now: bool = False):
    """rows: [(rel, size, mtime, kind)] of the chosen files, kind knowledge|files. Returns (first, order, est):
    first = the set of knowledge paths read first; order = every path, first pass first, then the rest
    smallest first; est = {first_files, first_seconds, rest_files, rest_seconds, big_files, big_bytes}.
    Files kept as files (music, pictures) cost no reading; they come after the first pass."""
    now = now or time.time()
    named = [n.strip("/").lower() for n in named if isinstance(n, str) and n.strip("/")]

    def in_named(rel):
        low = rel.lower()
        return any(low == n or low.startswith(n + "/") or f"/{n}/" in f"/{low}" for n in named)

    know = [r for r in rows if r[3] == "knowledge"]
    big = [r for r in know if is_big(r[0], r[1])]
    cand = [r for r in know if big_now or not is_big(r[0], r[1])]
    # named folders first, then recent, then the smallest; a big file never jumps the queue
    cand.sort(key=lambda r: (not in_named(r[0]), now - r[2] > RECENT_SECONDS, r[1], r[0]))
    first, spent = [], 0.0
    for r in cand:
        s = read_seconds(r[0], r[1])
        if spent + s > budget:
            continue  # a smaller one later may still fit
        first.append(r[0])
        spent += s
    fs = set(first)
    rest = sorted((r for r in know if r[0] not in fs), key=lambda r: (r[1], r[0]))
    kept = sorted((r for r in rows if r[3] != "knowledge"), key=lambda r: (r[1], r[0]))
    order = first + [r[0] for r in kept] + [r[0] for r in rest]
    rest_s = sum(read_seconds(r[0], r[1]) for r in rest)
    return fs, order, {"first_files": len(first), "first_seconds": round(spent), "rest_files": len(rest),
                       "rest_seconds": round(rest_s), "big_files": len(big), "big_bytes": sum(r[1] for r in big),
                       "kept_files": len(kept)}


# ── 3. one true count ──
def split_waiting(filenames, chat_re) -> dict:
    """Pending document proposals by their filename: {documents, chats, total}. chat_re: the server's one
    rule for a conversation document (api/chat_continue.py CHAT_DOC)."""
    chats = sum(1 for f in filenames if chat_re.search(str(f or "")))
    total = len(filenames)
    return {"documents": total - chats, "chats": chats, "total": total}


def eta_seconds(left_names_sizes) -> int:
    return int(sum(read_seconds(n, s) + PACE_SECONDS for n, s in left_names_sizes))


# ── 4. refusals by reason ──
REASONS = ("too_big", "type", "busy", "gone", "other")
RETRYABLE = {"busy", "other"}


def refusal_reason(code: int | str, detail: str = "") -> str:
    try:
        c = int(code)
    except (TypeError, ValueError):
        c = 0
    if c == 413:
        return "too_big"
    if c == 415:
        return "type"
    if c in (0, 429, 502, 503, 504):
        return "busy"
    if c == 404:
        return "gone"
    return "other"


def tally_refused(rows) -> dict:
    """rows: [{path, reason}] -> {reason: count} over REASONS, zeros left out."""
    out = {}
    for r in rows:
        k = r.get("reason") if r.get("reason") in REASONS else "other"
        out[k] = out.get(k, 0) + 1
    return out


class ReadGate:
    """The upload path's reading slots: UPLOAD_READERS read at once, UPLOAD_QUEUE more may wait for a slot;
    a file beyond that gets "wait" (503, Retry-After) and the agent sends it again later."""

    def __init__(self, readers: int = UPLOAD_READERS, queue: int = UPLOAD_QUEUE):
        self._sem = threading.BoundedSemaphore(readers)
        self._lock = threading.Lock()
        self._waiting = 0
        self.queue = queue

    def enter(self, timeout: float = 30.0) -> bool:
        with self._lock:
            if self._waiting >= self.queue:
                return False
            self._waiting += 1
        try:
            return self._sem.acquire(timeout=timeout)
        finally:
            with self._lock:
                self._waiting -= 1

    def leave(self) -> None:
        self._sem.release()


class ChatClock:
    """When a chat last ran (or is running), so the background reading steps aside."""

    def __init__(self):
        self._lock = threading.Lock()
        self.active = 0
        self.last = 0.0

    def begin(self):
        with self._lock:
            self.active += 1
            self.last = time.monotonic()

    def end(self):
        with self._lock:
            self.active = max(0, self.active - 1)
            self.last = time.monotonic()

    def busy(self, quiet: float = CHAT_QUIET_SECONDS) -> bool:
        with self._lock:
            return self.active > 0 or time.monotonic() - self.last < quiet

    def wait_quiet(self, sleep=time.sleep, max_wait: float = CHAT_WAIT_MAX) -> float:
        t0 = time.monotonic()
        while self.busy() and time.monotonic() - t0 < max_wait:
            sleep(1.0)
        return time.monotonic() - t0


def kind_matches(filename: str, kind: str, chat_re) -> bool:
    """approve-all's kind: documents (not conversations), chats, or all."""
    if kind == "chats":
        return bool(chat_re.search(filename or ""))
    if kind == "documents":
        return not chat_re.search(filename or "")
    return True


def reading_order(items, first_names, size_of):
    """The worker's order: the first pass first (laptop/<path> names), then the smallest first."""
    first_names = set(first_names or ())
    def key(p):
        name = (p.get("source_refs") or {}).get("filename") or ""
        return (name not in first_names, size_of(p), name)
    return sorted(items, key=key)
