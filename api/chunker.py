"""Chunking for the embedder (2026-11-10, CHUNK-1).

The word chunker cut 500-word windows every 450 words. On this operator's markdown a 500-word
window is 787 to 1,283 bge tokens (measured 2026-11-06), and bge-large reads 512, so the
embedding saw roughly the first 210 words of each chunk and words ~210-450 of every stride
were in no vector at all; the 50-word overlap sat past the cut and did nothing.

The token chunker splits on markdown headings, then paragraphs, then sentences, then words,
and packs pieces into chunks of at most CHUNK_MAX_TOKENS tokens counted by the embedding
model's own tokenizer (special tokens excluded; 480 leaves room for [CLS]/[SEP] under 512).
Every chunk starts with its heading path, so a section's later chunks still say where they
are. Within a section a new chunk repeats up to CHUNK_OVERLAP_TOKENS of the previous one's
tail (whole sentences when they fit); a new section starts clean.

CHUNKER=words (the default) keeps the old behaviour, so no live brain changes its chunks
until the owner sets CHUNKER=tokens. Existing rows are not touched: the new chunks apply to
what is ingested or re-ingested afterwards (a re-ingest re-embeds that document whole,
since its chunk hashes change; api/chunk_diff.py).
"""
from __future__ import annotations

import os
import re
import threading
from typing import Callable, List, Optional, Tuple

Counter = Callable[[str], int]

DEFAULT_MAX_TOKENS = 480
DEFAULT_OVERLAP_TOKENS = 48


def mode() -> str:
    """'words' (default, the old chunker) or 'tokens'."""
    m = os.environ.get("CHUNKER", "words").strip().lower()
    return m if m in ("words", "tokens") else "words"


def max_tokens() -> int:
    return int(os.environ.get("CHUNK_MAX_TOKENS", str(DEFAULT_MAX_TOKENS)))


def overlap_tokens() -> int:
    return int(os.environ.get("CHUNK_OVERLAP_TOKENS", str(DEFAULT_OVERLAP_TOKENS)))


# ── the old chunker, unchanged ───────────────────────────────────────────────

def word_chunks(text: str, chunk_size: int = 500, overlap: int = 50) -> List[str]:
    """Split text into overlapping chunks for better embeddings"""
    words = text.split()
    chunks = []

    for i in range(0, len(words), chunk_size - overlap):
        chunk = " ".join(words[i:i + chunk_size])
        if chunk.strip():
            chunks.append(chunk.strip())

    return chunks


# ── the tokenizer ────────────────────────────────────────────────────────────

_tok_lock = threading.Lock()
_counter: Optional[Counter] = None


def _counter_from_tokenizer(tok) -> Counter:
    """A count function over a `tokenizers.Tokenizer`, on a private copy with truncation and
    padding off (a shared fast tokenizer keeps the 512 truncation of its last call)."""
    from tokenizers import Tokenizer
    own = Tokenizer.from_str(tok.to_str())
    own.no_truncation()
    own.no_padding()
    return lambda s: len(own.encode(s, add_special_tokens=False).ids)


def load_counter() -> Counter:
    """The embedding model's tokenizer as a count function. The in-process model's tokenizer
    when it is loaded, else the model's tokenizer.json (a local path or the Hugging Face cache).
    Raises when neither is available."""
    global _counter
    if _counter is not None:
        return _counter
    with _tok_lock:
        if _counter is not None:
            return _counter
        name = os.environ.get("EMBEDDING_MODEL_NAME", "BAAI/bge-large-en-v1.5")
        try:
            from api.embeddings import model as _em
            if _em.is_model_loaded():
                _counter = _counter_from_tokenizer(_em.get_model().tokenizer.backend_tokenizer)
                return _counter
        except Exception:
            pass
        from tokenizers import Tokenizer
        if os.path.isdir(name):
            path = os.path.join(name, "tokenizer.json")
        else:
            from huggingface_hub import hf_hub_download
            path = hf_hub_download(name, "tokenizer.json")
        _counter = _counter_from_tokenizer(Tokenizer.from_file(path))
        return _counter


# ── the token chunker ────────────────────────────────────────────────────────

_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_FENCE = re.compile(r"^\s*(```|~~~)")
_SENTENCE = re.compile(r"(?<=[.!?;:])\s+(?=\S)")


def _sections(text: str) -> List[Tuple[str, List[str]]]:
    """[(heading path, [blocks])]. A block is a paragraph, a list run or a fenced code block
    (blank-line separated, fences kept whole). The heading path is the chain of headings
    above the section, e.g. '# Guide > ## Install'; '' before the first heading."""
    out: List[Tuple[str, List[str]]] = []
    stack: List[Tuple[int, str]] = []
    blocks: List[str] = []
    cur: List[str] = []
    in_fence = False

    def flush_block():
        if cur and "".join(cur).strip():
            blocks.append("\n".join(cur).strip("\n"))
        cur.clear()

    def flush_section():
        flush_block()
        path = " > ".join(h for _, h in stack)
        if blocks:
            out.append((path, list(blocks)))
        blocks.clear()

    for line in text.replace("\r\n", "\n").split("\n"):
        if _FENCE.match(line):
            in_fence = not in_fence
            cur.append(line)
            if not in_fence:
                flush_block()
            continue
        if in_fence:
            cur.append(line)
            continue
        m = _HEADING.match(line)
        if m:
            flush_section()
            level = len(m.group(1))
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, f"{m.group(1)} {m.group(2)}"))
            continue
        if not line.strip():
            flush_block()
        else:
            cur.append(line)
    flush_section()
    # A heading with no body (e.g. the title right above a sub-heading) still names the
    # sections under it through the path; a document of headings only keeps them as text.
    if not out and stack:
        out.append(("", [" > ".join(h for _, h in stack)]))
    return out


def _split_to_fit(piece: str, budget: int, count: Counter) -> List[str]:
    """Split one piece that is over budget: by lines, then sentences, then words."""
    if count(piece) <= budget:
        return [piece]
    for splitter in (lambda s: s.split("\n"), lambda s: _SENTENCE.split(s)):
        parts = [p for p in splitter(piece) if p.strip()]
        if len(parts) > 1:
            out: List[str] = []
            for p in parts:
                out.extend(_split_to_fit(p, budget, count))
            return out
    # words, greedily; a single word over budget (a long URL or hash) is cut by characters
    words = piece.split()
    out, cur = [], []
    for w in words:
        if count(w) > budget:
            if cur:
                out.append(" ".join(cur))
                cur = []
            step = max(1, len(w) // max(2, count(w) // budget + 1))
            out.extend(_split_to_fit_chars(w, budget, count, step))
            continue
        if cur and count(" ".join(cur + [w])) > budget:
            out.append(" ".join(cur))
            cur = [w]
        else:
            cur.append(w)
    if cur:
        out.append(" ".join(cur))
    return out


def _split_to_fit_chars(word: str, budget: int, count: Counter, step: int) -> List[str]:
    out, i = [], 0
    while i < len(word):
        j = min(len(word), i + step)
        while j > i + 1 and count(word[i:j]) > budget:
            j = i + max(1, (j - i) // 2)
        out.append(word[i:j])
        i = j
    return out


def _tail(text: str, budget: int, count: Counter) -> str:
    """The end of `text` within `budget` tokens: whole sentences when they fit, else words."""
    if budget <= 0 or not text.strip():
        return ""
    sentences = [s for s in _SENTENCE.split(text.replace("\n", " ")) if s.strip()]
    picked: List[str] = []
    for s in reversed(sentences):
        if count(" ".join([s] + picked)) > budget:
            break
        picked.insert(0, s)
    if picked:
        return " ".join(picked)
    words = text.split()
    picked = []
    for w in reversed(words):
        if count(" ".join([w] + picked)) > budget:
            break
        picked.insert(0, w)
    return " ".join(picked)


def token_chunks(text: str, count: Optional[Counter] = None, max_tok: Optional[int] = None,
                 overlap: Optional[int] = None) -> List[str]:
    """Heading-aware chunks of at most `max_tok` tokens by `count` (the embedding tokenizer)."""
    count = count or load_counter()
    max_tok = max_tokens() if max_tok is None else max_tok
    overlap = overlap_tokens() if overlap is None else overlap
    overlap = max(0, min(overlap, max_tok // 4))
    chunks: List[str] = []
    for path, blocks in _sections(text):
        head = path + "\n\n" if path else ""
        head_tok = count(head) if head else 0
        if head_tok > max_tok // 2:       # an absurdly long heading path: keep its last heading
            head = path.split(" > ")[-1][: 200] + "\n\n"
            head_tok = count(head)
        budget = max_tok - head_tok
        pieces: List[str] = []
        for b in blocks:
            pieces.extend(_split_to_fit(b, budget - overlap, count) if count(b) > budget - overlap else [b])
        body: List[str] = []
        body_tok = 0
        for p in pieces:
            p_tok = count(p)
            if body and body_tok + p_tok > budget:
                done = "\n\n".join(body)
                chunks.append(head + done)
                carry = _tail(done, overlap, count)
                if carry and count(carry) + p_tok > budget:
                    carry = ""
                body = [carry] if carry else []
            body.append(p)
            body_tok = count("\n\n".join(body))
        if body:
            chunks.append(head + "\n\n".join(body))
    # The cap is a guarantee, not a hope: re-count every chunk and split any that slipped over.
    final: List[str] = []
    for c in chunks:
        c = c.strip()
        if not c:
            continue
        if count(c) <= max_tok:
            final.append(c)
        else:
            final.extend(x for x in _split_to_fit(c, max_tok, count) if x.strip())
    return final


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> List[str]:
    """The ingest chunker. CHUNKER=words (default): 500-word windows every 450 words, as
    before. CHUNKER=tokens: token_chunks under CHUNK_MAX_TOKENS. If the tokenizer cannot be
    loaded the word chunker is used and the reason printed, so ingest never fails over it."""
    if mode() == "tokens":
        try:
            return token_chunks(text)
        except Exception as e:
            print(f"[chunker] CHUNKER=tokens but the tokenizer is unavailable ({type(e).__name__}: {e}); "
                  f"word chunks this time", flush=True)
    return word_chunks(text, chunk_size, overlap)
