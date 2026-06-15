"""
api/json_utils.py — robust JSON extraction from LLM output.

Models occasionally wrap JSON in ```fences```, lead with prose, or truncate
mid-object. `extract_json_object` strips fences then brace-balances to find the
longest well-formed {...} block. Lifted out of /memory/store/propose so the
onboarding fact-extractor and the store-button classifier share one parser.
"""
from __future__ import annotations

import json
import re
from typing import Optional


def strip_code_fences(s: str) -> str:
    s = (s or "").strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s)
        s = re.sub(r"\s*```\s*$", "", s)
    return s


def extract_json_object(s: str) -> Optional[object]:
    """Find the longest substring starting with '{' that parses as JSON.
    Handles preamble prose and trailing junk. Returns the parsed object or
    None if no valid JSON object is found."""
    start_positions = [i for i, c in enumerate(s) if c == '{']
    for start in start_positions:
        depth = 0
        in_str = False
        esc = False
        for i in range(start, len(s)):
            ch = s[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == '\\':
                    esc = True
                elif ch == '"':
                    in_str = False
            else:
                if ch == '"':
                    in_str = True
                elif ch == '{':
                    depth += 1
                elif ch == '}':
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(s[start:i + 1])
                        except json.JSONDecodeError:
                            break
    return None


def parse_json_loose(raw: str) -> Optional[object]:
    """Best-effort: try a clean parse after stripping fences, then fall back to
    the brace-balancing extractor. Returns None if nothing parses."""
    text = strip_code_fences(raw)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return extract_json_object(text)
