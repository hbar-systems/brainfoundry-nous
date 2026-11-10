#!/usr/bin/env python3
"""Recall@k of the brain's retrieval under the word chunker and the token chunker (2026-11-10).

Embeds a copy of a corpus under both chunkers (api/chunker.py: word_chunks, token_chunks),
holds the vectors in memory, ranks every chunk by cosine against each golden question (the
brain ranks by L2 on unit vectors, the same order), and counts a hit when one of the top k
chunks contains the question's answer span (whitespace-collapsed). No database, no brain, no
writes outside --cache.

Golden set: JSONL, one {"question", "answer", "doc"} per line; "answer" is a verbatim span of
the document "doc" (a path under --root). The corpus is --corpus (one path per line, under
--root) or, without it, the documents the golden set names. The private set for the
operator's own documents lives outside this repo (tests/golden/README.md).

Embedder: the in-process sentence-transformers model (as the brain runs it) when installed;
or --onnx MODEL.onnx with --tokenizer tokenizer.json (CLS pooling, unit length: bge's own
pooling), for a box without torch. Inputs are cut at 512 tokens, as the model does.

  python3 scripts/eval_retrieval.py --golden G.jsonl --root /path/to/world \\
      [--corpus corpus.txt] [--onnx model.onnx --tokenizer tokenizer.json] \\
      [--k 5] [--cache /tmp/eval-cache] [--max-tokens 480] [--overlap 48] [--json out.json]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from api.chunker import _counter_from_tokenizer, token_chunks, word_chunks  # noqa: E402

MODEL = os.environ.get("EMBEDDING_MODEL_NAME", "BAAI/bge-large-en-v1.5")


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


class Embedder:
    def __init__(self, onnx: str | None, tokenizer: str | None, threads: int):
        import numpy as np
        self.np = np
        from tokenizers import Tokenizer
        if onnx:
            import onnxruntime as ort
            if not tokenizer:
                sys.exit("--onnx needs --tokenizer")
            so = ort.SessionOptions()
            so.intra_op_num_threads = threads
            self.sess = ort.InferenceSession(onnx, so, providers=["CPUExecutionProvider"])
            self.inputs = {i.name for i in self.sess.get_inputs()}
            self.tok = Tokenizer.from_file(tokenizer)
            self.tok.enable_truncation(512)
            self.st = None
            self.counter = _counter_from_tokenizer(Tokenizer.from_file(tokenizer))
            self.name = f"onnx:{Path(onnx).name}"
        else:
            from sentence_transformers import SentenceTransformer
            self.st = SentenceTransformer(MODEL)
            self.counter = _counter_from_tokenizer(self.st.tokenizer.backend_tokenizer)
            self.name = f"sentence-transformers:{MODEL}"

    def encode(self, texts):
        np = self.np
        if self.st is not None:
            return np.asarray(self.st.encode(list(texts), normalize_embeddings=True), dtype=np.float32)
        self.tok.enable_padding()
        enc = self.tok.encode_batch(list(texts))
        ids = np.array([e.ids for e in enc], dtype=np.int64)
        mask = np.array([e.attention_mask for e in enc], dtype=np.int64)
        feed = {"input_ids": ids, "attention_mask": mask}
        if "token_type_ids" in self.inputs:
            feed["token_type_ids"] = np.zeros_like(ids)
        cls = self.sess.run(None, feed)[0][:, 0, :]
        return (cls / np.linalg.norm(cls, axis=1, keepdims=True)).astype(np.float32)


def embed_all(emb: Embedder, texts, cache: Path | None, batch: int, label: str):
    """Vectors for texts, cached by text hash; batches sorted by length so padding stays small."""
    np = emb.np
    store = {}
    cfile = None
    if cache:
        cache.mkdir(parents=True, exist_ok=True)
        cfile = cache / f"{re.sub(r'[^A-Za-z0-9_.-]', '_', emb.name)}.npz"
        if cfile.exists():
            d = np.load(cfile)
            store = {k: d[k] for k in d.files}
    key = lambda t: hashlib.sha256(t.encode()).hexdigest()[:32]
    todo = sorted({t for t in texts if key(t) not in store}, key=len)
    t0 = time.time()
    for i in range(0, len(todo), batch):
        part = todo[i:i + batch]
        for t, v in zip(part, emb.encode(part)):
            store[key(t)] = v
        done = min(i + batch, len(todo))
        print(f"  [{label}] embedded {done}/{len(todo)} new texts, {time.time() - t0:.0f}s", flush=True)
        if cfile and (done % (batch * 8) == 0 or done == len(todo)):
            np.savez(cfile, **store)
    return np.stack([store[key(t)] for t in texts]) if texts else np.zeros((0, 1024), np.float32)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--golden", default="tests/golden/retrieval.jsonl")
    ap.add_argument("--root", required=True, help="the directory the golden docs and corpus paths are under")
    ap.add_argument("--corpus", help="file of corpus paths, one per line (default: the golden docs)")
    ap.add_argument("--onnx")
    ap.add_argument("--tokenizer")
    ap.add_argument("--threads", type=int, default=os.cpu_count() or 4)
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--max-tokens", type=int, default=480)
    ap.add_argument("--overlap", type=int, default=48)
    ap.add_argument("--cache")
    ap.add_argument("--chunks-only", action="store_true", help="chunk and embed the corpus, no questions")
    ap.add_argument("--json", help="write the numbers here as JSON too")
    a = ap.parse_args()

    root = Path(a.root)
    golden = [] if a.chunks_only else [json.loads(l) for l in open(a.golden) if l.strip()]
    paths = [l.strip() for l in open(a.corpus) if l.strip()] if a.corpus else sorted({g["doc"] for g in golden})
    docs = {p: (root / p).read_text(errors="replace") for p in paths}
    emb = Embedder(a.onnx, a.tokenizer, a.threads)
    cache = Path(a.cache) if a.cache else None
    print(f"embedder {emb.name}; corpus {len(docs)} files, {sum(len(t.split()) for t in docs.values())} words; "
          f"{len(golden)} questions; k={a.k}", flush=True)

    arms = {
        "words": lambda t: word_chunks(t),
        "tokens": lambda t: token_chunks(t, emb.counter, a.max_tokens, a.overlap),
    }
    results = {"embedder": emb.name, "files": len(docs), "questions": len(golden), "k": a.k, "arms": {}}
    qvec = emb.encode([g["question"] for g in golden]) if golden else None
    for arm, fn in arms.items():
        chunks = [(p, c) for p, t in docs.items() for c in fn(t)]
        toks = [emb.counter(c) for _, c in chunks]
        over = sum(1 for n in toks if n > 510)
        print(f"{arm}: {len(chunks)} chunks, tokens min {min(toks)} mean {sum(toks) // len(toks)} max {max(toks)}, "
              f"{over} over 510 (truncated by the model)", flush=True)
        vecs = embed_all(emb, [c for _, c in chunks], cache, a.batch, arm)
        r = {"chunks": len(chunks), "tokens_mean": sum(toks) // len(toks), "tokens_max": max(toks),
             "chunks_over_510": over}
        if golden:
            normed = [norm(c) for _, c in chunks]
            sims = qvec @ vecs.T
            hits, hits1, reachable, rr = 0, 0, 0, 0.0
            per = []
            for gi, g in enumerate(golden):
                ans = norm(g["answer"])
                holders = {i for i, c in enumerate(normed) if ans in c}
                reachable += bool(holders)
                order = (-sims[gi]).argsort()
                rank = next((r_ + 1 for r_, i in enumerate(order) if i in holders), None)
                hits += bool(rank and rank <= a.k)
                hits1 += rank == 1
                rr += 1.0 / rank if rank else 0.0
                per.append(rank)
            n = len(golden)
            r.update({f"recall@{a.k}": round(hits / n, 4), "recall@1": round(hits1 / n, 4),
                      "mrr": round(rr / n, 4), "answer_reachable": reachable, "ranks": per})
            print(f"{arm}: recall@{a.k} {hits}/{n} = {hits / n:.3f}; recall@1 {hits1 / n:.3f}; "
                  f"MRR {rr / n:.3f}; answer whole in some chunk {reachable}/{n}", flush=True)
        results["arms"][arm] = r
    if a.json:
        Path(a.json).write_text(json.dumps(results, indent=1))


if __name__ == "__main__":
    main()
