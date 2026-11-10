"""The ingest chunker (api/chunker.py, 2026-11-10): the word chunker stays the default; the
token chunker never exceeds its cap, keeps headings, overlaps within a section, loses no text.

Most tests count tokens with a stand-in (words and punctuation marks, the way bge's BERT
pre-tokenizer splits before word pieces); one test uses the real bge tokenizer when the
`tokenizers` package and the model's tokenizer.json are on this machine.

Run from repo root:
    pytest tests/test_chunker.py -v
"""
from __future__ import annotations

import glob
import os
import random
import re

import pytest

from api import chunker
from api.chunker import chunk_text, token_chunks, word_chunks


def count(s: str) -> int:
    return len(re.findall(r"\w+|[^\w\s]", s))


def words_of(s: str) -> set:
    return set(re.findall(r"\w+", s))


def para(n: int, seed: int) -> str:
    rnd = random.Random(seed)
    vocab = ["memory", "brain", "chunk", "token", "vector", "gate", "permit", "ledger", "steward",
             "federation", "harmonics", "embedding", "recall", "golden", "corpus", "box", "spoke"]
    out = []
    for i in range(n):
        out.append(rnd.choice(vocab) + f"{seed}x{i}")
        if i % 12 == 11:
            out[-1] += "."
    return " ".join(out) + "."


DOC = "\n\n".join([
    "# Guide",
    "Intro paragraph about the guide. " + para(60, 1),
    "## Install",
    para(150, 2),
    para(150, 3),
    para(150, 4),
    "### Pitfalls",
    "- first pitfall " + para(20, 5) + "\n- second pitfall " + para(20, 6),
    "## Use",
    "```\ncode line one\ncode line two\n```",
    para(400, 7),     # one paragraph far over the cap
])


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for k in ("CHUNKER", "CHUNK_MAX_TOKENS", "CHUNK_OVERLAP_TOKENS"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(chunker, "_counter", None)


def test_default_is_the_old_word_chunker():
    text = para(1200, 9)
    assert chunker.mode() == "words"
    assert chunk_text(text) == word_chunks(text)
    w = text.split()
    old = [" ".join(w[i:i + 500]) for i in range(0, len(w), 450)]
    assert chunk_text(text) == old


def test_unknown_mode_falls_back_to_words(monkeypatch):
    monkeypatch.setenv("CHUNKER", "bogus")
    assert chunker.mode() == "words"


def test_main_chunk_text_goes_through_the_chunker(monkeypatch):
    # main refuses to start without an identity secret; scratch runtime off-container (as test_ask)
    import tempfile
    rt = tempfile.mkdtemp(prefix="chunker-test-")
    os.environ.setdefault("BRAIN_IDENTITY_SECRET", "test-only-secret")
    os.environ.setdefault("BRAIN_RUNTIME_DIR", rt)
    os.environ.setdefault("SETTINGS_PATH", os.path.join(rt, "settings.json"))
    from api import main
    text = DOC
    assert main.chunk_text(text) == word_chunks(text)
    monkeypatch.setenv("CHUNKER", "tokens")
    monkeypatch.setattr(chunker, "_counter", count)
    assert main.chunk_text(text) == token_chunks(text, count, 480, 48)


@pytest.mark.parametrize("cap,overlap", [(480, 48), (120, 16), (60, 0), (40, 10)])
def test_no_chunk_exceeds_the_cap(cap, overlap):
    chunks = token_chunks(DOC, count, cap, overlap)
    assert chunks
    assert max(count(c) for c in chunks) <= cap


def test_cap_holds_for_a_wall_of_text_and_a_huge_word():
    text = para(3000, 11).replace(".", "") + " " + "a" * 5000 + " " + "https://x.example/" + "q=1&" * 600
    chunks = token_chunks(text, count, 100, 20)
    assert max(count(c) for c in chunks) <= 100


def test_no_text_is_lost():
    chunks = token_chunks(DOC, count, 120, 16)
    seen = set().union(*(words_of(c) for c in chunks))
    assert words_of(DOC) <= seen


def test_every_chunk_starts_with_its_heading_path():
    chunks = token_chunks(DOC, count, 120, 16)
    install = [c for c in chunks if c.startswith("# Guide > ## Install\n")]
    pitfalls = [c for c in chunks if c.startswith("# Guide > ## Install > ### Pitfalls\n")]
    use = [c for c in chunks if c.startswith("# Guide > ## Use\n")]
    assert len(install) >= 3 and pitfalls and len(use) >= 2
    # every chunk carries a heading path, since the document starts with a heading
    assert all(c.startswith("# Guide") for c in chunks)
    # a sibling heading closes the deeper one
    assert not any("### Pitfalls" in c.split("\n")[0] and "## Use" in c.split("\n")[0] for c in chunks)


def test_code_fence_kept_whole():
    chunks = token_chunks(DOC, count, 120, 16)
    assert any("```\ncode line one\ncode line two\n```" in c for c in chunks)
    doc = "# T\n\n```\n# not a heading\n```\n\nafter"
    out = token_chunks(doc, count, 480, 48)
    assert len(out) == 1 and "# not a heading" in out[0] and out[0].startswith("# T\n")


def test_overlap_within_a_section_not_across():
    chunks = token_chunks(DOC, count, 120, 16)
    install = [c.split("\n\n", 1)[1] for c in chunks if c.startswith("# Guide > ## Install\n")]
    for a, b in zip(install, install[1:]):
        tail_words = a.split()[-3:]
        assert " ".join(tail_words) in b, "the next chunk repeats the end of the previous one"
    # the first Use chunk does not repeat the end of the last Pitfalls chunk
    first_use = next(c for c in chunks if c.startswith("# Guide > ## Use\n"))
    last_pit = [c for c in chunks if c.startswith("# Guide > ## Install > ### Pitfalls\n")][-1]
    assert " ".join(last_pit.split()[-3:]) not in first_use


def test_overlap_zero_means_no_repeat():
    chunks = token_chunks(para(600, 12), count, 100, 0)
    body = [c.split() for c in chunks]
    for a, b in zip(body, body[1:]):
        assert a[-1] != b[0]


def test_overlap_is_bounded_by_its_setting():
    chunks = token_chunks(para(900, 13), count, 100, 20)
    total = sum(count(c) for c in chunks)
    assert total <= count(para(900, 13)) + 20 * (len(chunks) - 1) + len(chunks)


def test_settings_from_env(monkeypatch):
    monkeypatch.setenv("CHUNKER", "tokens")
    monkeypatch.setenv("CHUNK_MAX_TOKENS", "90")
    monkeypatch.setenv("CHUNK_OVERLAP_TOKENS", "9")
    monkeypatch.setattr(chunker, "_counter", count)
    chunks = chunk_text(DOC)
    assert chunks == token_chunks(DOC, count, 90, 9)
    assert max(count(c) for c in chunks) <= 90


def test_tokens_mode_without_a_tokenizer_falls_back_to_words(monkeypatch, capsys):
    monkeypatch.setenv("CHUNKER", "tokens")

    def broken():
        raise OSError("no tokenizer here")
    monkeypatch.setattr(chunker, "load_counter", broken)
    assert chunk_text(DOC) == word_chunks(DOC)
    assert "word chunks this time" in capsys.readouterr().out


def test_empty_and_heading_only_text():
    assert token_chunks("", count, 480, 48) == []
    assert token_chunks("   \n\n  ", count, 480, 48) == []
    assert token_chunks("# Only a title", count, 480, 48) == ["# Only a title"]


def _bge_tokenizer_json():
    hits = glob.glob(os.path.expanduser(
        "~/.cache/huggingface/hub/models--BAAI--bge-large-en-v1.5/snapshots/*/tokenizer.json"))
    return hits[0] if hits else None


def test_real_bge_tokens_stay_under_512():
    tokenizers = pytest.importorskip("tokenizers")
    path = _bge_tokenizer_json()
    if not path:
        pytest.skip("bge tokenizer.json not in the Hugging Face cache")
    real = chunker._counter_from_tokenizer(tokenizers.Tokenizer.from_file(path))
    text = DOC + "\n\n" + "## Table\n\n| a | b |\n|---|---|\n" + "\n".join(f"| row{i} | `x_{i}` |" for i in range(300))
    chunks = token_chunks(text, real, 480, 48)
    assert max(real(c) for c in chunks) <= 480
    old = word_chunks(text)
    assert max(real(c) for c in old) > 512   # the reason for all this
