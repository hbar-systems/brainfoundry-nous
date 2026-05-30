"""
api/injection_scan.py — flag prompt-injection attempts in ingested documents.

Cognitive-OS gap #3. A brain's ingest is trusted by default: a poisoned PDF,
scraped page, or forwarded email can carry text aimed not at the reader but at
the MODEL — "ignore your instructions", "reveal your system prompt", a forged
`System:` turn, invisible zero-width instructions. Once embedded, that text can
be retrieved into a later answer's context and treated as a command.

This module scans extracted document text for those patterns and returns a risk
assessment. It does NOT block — the brain's ingest is a propose→approve flow, so
the right move is to surface the risk to the operator at approval time and let
them decide. It is a heuristic detector, not a guarantee; it raises the cost of
the obvious attacks and makes a poisoned document visible before it lands in
memory. The structural backstop (retrieved documents are framed as reference,
never as commands) lives in the RAG prompt in main.py.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Dict, List

# Severity → points. Score is the capped sum; bands derive from it.
_SEV_POINTS = {"high": 40, "medium": 20, "low": 8}
_HIDDEN_POINTS = 25  # invisible-character payloads

# (label, severity, compiled pattern). Case-insensitive, matched per document.
_PATTERNS = [
    ("ignore-previous", "high",
     r"\b(ignore|disregard|forget)\b[^.\n]{0,30}\b(previous|prior|earlier|above|all|your)\b[^.\n]{0,30}\b(instruction|instructions|prompt|prompts|rule|rules|context|message|messages)\b"),
    ("reveal-system", "high",
     r"\b(reveal|print|repeat|show|output|display|tell me|give me|what (is|are))\b[^.\n]{0,30}\b(system prompt|initial instructions?|your instructions?|your prompt|hidden prompt|api key|secret key|password)\b"),
    ("role-override", "high",
     r"\b(you are|act|behave|respond)\b[^.\n]{0,20}\b(now |no longer )?\b(DAN|jailbroken|jailbreak|in developer mode|unrestricted|without (any )?(restrictions?|filters?|rules?))\b"),
    ("from-now-on", "high",
     r"\bfrom now on,?\b[^.\n]{0,30}\byou\b[^.\n]{0,20}\b(are|will|must|should|shall|have to)\b"),
    ("new-instructions", "high",
     r"\b(new|updated|revised|real|true|actual)\b[^.\n]{0,15}\b(instructions?|directives?|system prompt|task)\b\s*[:：]"),
    ("override-rules", "high",
     r"\boverride\b[^.\n]{0,20}\b(your |the )?(instructions?|rules?|safety|guidelines?|system|settings)\b"),
    ("keep-secret", "medium",
     r"\b(do not|don't|never)\b[^.\n]{0,20}\b(tell|reveal|mention|inform|warn|alert|notify)\b[^.\n]{0,20}\b(the user|anyone|them|your owner|operator)\b"),
    ("pretend", "medium",
     r"\b(pretend|imagine|roleplay|role-play)\b[^.\n]{0,15}\b(you are|to be|that you|you're)\b"),
    ("forged-turn", "medium",
     r"(?m)^\s*(system|assistant|user)\s*[:：]\s+\S"),
    ("chat-template-marker", "medium",
     r"(<\|im_start\|>|<\|im_end\|>|\[/?INST\]|<<SYS>>|###\s*(instruction|system))"),
    ("without-permission", "low",
     r"\bwithout\b[^.\n]{0,15}\b(asking|confirmation|permission|telling|notifying)\b"),
    ("instruction-to-ai", "low",
     r"\b(as an? (ai|assistant|language model)|to the (ai|assistant|model)|attention,? (ai|assistant|model))\b"),
]
_COMPILED = [(label, sev, re.compile(rx, re.IGNORECASE)) for label, sev, rx in _PATTERNS]

# Invisible / formatting characters used to smuggle hidden instructions.
_INVISIBLE = {
    "​": "ZERO WIDTH SPACE", "‌": "ZERO WIDTH NON-JOINER",
    "‍": "ZERO WIDTH JOINER", "⁠": "WORD JOINER",
    "﻿": "ZERO WIDTH NO-BREAK SPACE", "­": "SOFT HYPHEN",
    "‮": "RIGHT-TO-LEFT OVERRIDE", "‭": "LEFT-TO-RIGHT OVERRIDE",
}


def _excerpt(text: str, start: int, end: int, pad: int = 50) -> str:
    """A trimmed, whitespace-collapsed window around a match for display."""
    a = max(0, start - pad)
    b = min(len(text), end + pad)
    snippet = text[a:b].replace("\n", " ")
    snippet = re.sub(r"\s+", " ", snippet).strip()
    return (("…" if a > 0 else "") + snippet + ("…" if b < len(text) else ""))[:240]


def scan_text(text: str, max_signals: int = 20) -> Dict:
    """Scan document text for prompt-injection patterns.

    Returns {risk, score, signals, summary}. risk ∈ none/low/medium/high.
    `signals` is a capped, de-duplicated list of {label, severity, excerpt}.
    """
    if not text:
        return {"risk": "none", "score": 0, "signals": [], "summary": "No text to scan."}

    signals: List[Dict] = []
    score = 0
    seen = set()

    for label, sev, rx in _COMPILED:
        for m in rx.finditer(text):
            key = (label, m.start() // 40)  # collapse near-duplicate hits
            if key in seen:
                continue
            seen.add(key)
            score += _SEV_POINTS[sev]
            if len(signals) < max_signals:
                signals.append({
                    "label": label, "severity": sev,
                    "excerpt": _excerpt(text, m.start(), m.end()),
                })

    # Invisible-character payload check.
    invisible_hits = {}
    for ch in text:
        if ch in _INVISIBLE:
            invisible_hits[ch] = invisible_hits.get(ch, 0) + 1
    if invisible_hits:
        score += _HIDDEN_POINTS
        names = ", ".join(f"{_INVISIBLE[c]}×{n}" for c, n in invisible_hits.items())
        if len(signals) < max_signals:
            signals.append({
                "label": "invisible-characters", "severity": "high",
                "excerpt": f"Hidden/invisible characters present: {names}",
            })

    score = min(100, score)
    if score >= 60:
        risk = "high"
    elif score >= 25:
        risk = "medium"
    elif score >= 8:
        risk = "low"
    else:
        risk = "none"

    n = len(signals)
    if risk == "none":
        summary = "No prompt-injection patterns detected."
    else:
        summary = (f"{n} suspicious passage{'s' if n != 1 else ''} that look like "
                   f"instructions aimed at the AI — review before approving.")
    return {"risk": risk, "score": score, "signals": signals, "summary": summary}
