# Golden retrieval set

Created 2026-11-10 (CHUNK-1).

`scripts/eval_retrieval.py` measures recall@k of retrieval under the word chunker and the token
chunker (`api/chunker.py`) against a golden set: JSONL, one object per line,

    {"id": "g001", "question": "...", "answer": "<verbatim span of the document>", "doc": "<path under --root>"}

A retrieved chunk is a hit when it contains `answer` (whitespace collapsed), so the same set
scores any chunker.

A golden set is written from the owner's own documents, which are private, so it does not live
in this public repo. Put yours at `tests/golden/retrieval.jsonl` (git-ignored) or pass
`--golden`. Write questions the way the owner would ask, paraphrased, from passages picked at
random word positions, so answers fall wherever text falls in a document.

    python3 scripts/eval_retrieval.py --root /path/to/docs --golden tests/golden/retrieval.jsonl --k 5

Without torch, `--onnx model.onnx --tokenizer tokenizer.json` runs the same bge model through
onnxruntime (CLS pooling, unit length).
