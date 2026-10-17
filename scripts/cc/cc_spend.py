"""cc_spend: the brain's own spend meter. Created 2026-10-17.

Imported by cc-bridge.py (same directory). Standard library only.

What this brain spends, for its owner to see: one line per paid thing (a turn of the reasoner, a job,
an agent run, a paid tool call) in <bridge state dir>/spend.jsonl, append-only, never rewritten:

    {"date": "2026-10-17T09:12:00Z", "what": "turn", "provider": "Anthropic", "eur": 0.04, "tokens": 5100, "minutes": 0.3}

eur, tokens and minutes may be null when the place that spent does not know them (a job knows its
minutes, not its price). Totals add what is known. Beside it, spend-cap.json holds the owner's cap:
EUR for the last 30 days. Over the cap, scheduled agents wait and ask instead of running.

This is the person's view of their own spend. What anyone charges them for running the brain is
not here and does not belong in this file.
"""
from __future__ import annotations

import calendar
import json
import os
import threading
import time
from pathlib import Path

WHAT_MAX = 120
PROVIDER_MAX = 40
CAP_MAX_EUR = 100000.0
# The reasoner reports USD; the ledger keeps EUR. The owner may set their own rate (CC_EUR_PER_USD).
EUR_PER_USD = float(os.environ.get("CC_EUR_PER_USD") or 0.92)
WINDOWS = (("today", None), ("week", 7), ("month", 30))   # today is the UTC day; week and month are rolling days


def _iso(t: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))


def _ts(s) -> float | None:
    try:
        return float(calendar.timegm(time.strptime(str(s), "%Y-%m-%dT%H:%M:%SZ")))
    except (TypeError, ValueError):
        return None


def _num(v, where: str):
    if v is None:
        return None
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v < 0 or v != v:
        raise ValueError(f"{where} must be a number of zero or more, or empty")
    return v


class Ledger:
    def __init__(self, state_dir: Path):
        self.dir = Path(state_dir)
        self.path = self.dir / "spend.jsonl"
        self.cap_path = self.dir / "spend-cap.json"
        self.lock = threading.Lock()

    def append(self, what: str, provider: str, eur=None, usd=None, tokens=None, minutes=None, t: float | None = None,
               estimate: bool = False) -> dict:
        """Write one line. `usd` is converted when `eur` is not given. `estimate` marks a figure that is what
        the same work would cost at API prices (a subscription pays its plan, not this)."""
        what = " ".join(str(what or "").split())[:WHAT_MAX]
        provider = " ".join(str(provider or "").split())[:PROVIDER_MAX]
        if not what or not provider:
            raise ValueError("a spend line needs what and provider")
        eur, usd = _num(eur, "eur"), _num(usd, "usd")
        if eur is None and usd is not None:
            eur = usd * EUR_PER_USD
        tokens, minutes = _num(tokens, "tokens"), _num(minutes, "minutes")
        line = {"date": _iso(t if t is not None else time.time()), "what": what, "provider": provider,
                "eur": round(eur, 4) if eur is not None else None,
                "tokens": int(tokens) if tokens is not None else None,
                "minutes": round(minutes, 2) if minutes is not None else None}
        if estimate:
            line["estimate"] = True
        with self.lock:
            self.dir.mkdir(mode=0o700, parents=True, exist_ok=True)
            with self.path.open("a") as f:
                f.write(json.dumps(line) + "\n")
        return line

    def lines(self, since: float | None = None) -> list:
        out = []
        try:
            with self.path.open() as f:
                for raw in f:
                    try:
                        d = json.loads(raw)
                    except ValueError:
                        continue   # a torn line is skipped, never fatal
                    t = _ts(d.get("date")) if isinstance(d, dict) else None
                    if t is None or (since is not None and t < since):
                        continue
                    out.append({**d, "_t": t})
        except OSError:
            pass
        return out

    def totals(self, now: float | None = None) -> dict:
        now = time.time() if now is None else now
        day0 = now - (now % 86400)
        starts = {k: (day0 if days is None else now - days * 86400) for k, days in WINDOWS}
        out = {k: {"eur": 0.0, "tokens": 0, "minutes": 0.0, "count": 0, "estimate": False} for k in starts}
        for d in self.lines(since=min(starts.values())):
            for k, s in starts.items():
                if d["_t"] < s or d["_t"] > now + 60:
                    continue
                o = out[k]
                o["count"] += 1
                o["eur"] += float(d.get("eur") or 0)
                o["tokens"] += int(d.get("tokens") or 0)
                o["minutes"] += float(d.get("minutes") or 0)
                o["estimate"] = o["estimate"] or bool(d.get("estimate"))
        for o in out.values():
            o["eur"], o["minutes"] = round(o["eur"], 2), round(o["minutes"], 1)
        return out

    def cap(self) -> float | None:
        try:
            v = json.loads(self.cap_path.read_text()).get("eur")
            return float(v) if v is not None and float(v) >= 0 else None
        except (OSError, ValueError, TypeError, AttributeError):
            return None

    def set_cap(self, eur) -> float | None:
        """The owner's cap in EUR for the last 30 days; None takes it away."""
        if eur is not None:
            eur = _num(eur, "cap")
            if eur > CAP_MAX_EUR:
                raise ValueError(f"the cap must be at most {CAP_MAX_EUR:g} EUR")
            eur = round(float(eur), 2)
        with self.lock:
            self.dir.mkdir(mode=0o700, parents=True, exist_ok=True)
            tmp = self.cap_path.with_suffix(".tmp")
            tmp.write_text(json.dumps({"eur": eur, "set": _iso(time.time())}))
            tmp.replace(self.cap_path)
        return eur

    def over_cap(self, now: float | None = None) -> bool:
        cap = self.cap()
        return cap is not None and self.totals(now)["month"]["eur"] >= cap

    def view(self, now: float | None = None) -> dict:
        tot, cap = self.totals(now), self.cap()
        return {**tot, "cap": cap, "over": cap is not None and tot["month"]["eur"] >= cap, "eur_per_usd": EUR_PER_USD}
