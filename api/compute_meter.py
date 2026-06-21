"""compute_meter — read-only metering of LLM token consumption (v0).

The third economic register for hbar.systems: compute (LLM tokens) as the
internal rivalrous unit, alongside Harmonics (epistemic, non-transferable) and
fiat (external clearing). Architecture:
  hbar.world/discussions/2026-06-19_compute-token-as-rivalrous-register.md

This is READ-ONLY metering. No top-up, no enforcement, no billing, no harmonics
coupling. Goal: prove the unit is real and reconcile measured consumption
against real compute cost — the evidence the "cost-discovered, honest peg"
claim depends on.

Mirrors api/harmonics.py exactly: an append-only Postgres ledger, derived on
read, no stored balance. Because state is Postgres (DATABASE_URL), the
container-root-chown and template-tracked-runtime-state hazards do NOT apply —
DB state never touches the repo.

Created 2026-06-19.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Optional

import psycopg2
from fastapi import APIRouter, HTTPException


# ─── Rate table (config, not code) ──────────────────────────────────────────

_RATES_PATH = Path(__file__).parent / "compute_rates.json"

# Baked-in fallback so the meter works even if the JSON is missing. The JSON
# (operator-editable) wins when present. €/Mtoken, separate input/output.
_FALLBACK_RATES = {
    "claude-opus-4-8": {"in": 14.0, "out": 70.0},
    "claude-sonnet-4-6": {"in": 2.8, "out": 14.0},
    "claude-haiku-4-5": {"in": 0.75, "out": 3.7},
    "gpt-4o": {"in": 2.3, "out": 9.3},
    "llama3.2:3b": {"in": 0.04, "out": 0.04},
}


def _load_rates() -> dict:
    try:
        data = json.loads(_RATES_PATH.read_text(encoding="utf-8"))
        rates = data.get("rates")
        if isinstance(rates, dict) and rates:
            return rates
    except Exception as e:
        print(f"[compute_meter] rate table load failed, using fallback: {e}", flush=True)
    return _FALLBACK_RATES


def _rate_for(model: str) -> Optional[dict]:
    """Return {'in', 'out'} €/Mtoken for a model, or None if uncosted.

    Re-reads the JSON each call so the operator can edit the peg without a
    restart (low-frequency path; cost is negligible). A model absent from the
    table is uncosted -> est_cost_eur 0 + estimated stays visible.
    """
    return _load_rates().get(model)


def est_cost_eur(model: str, prompt_tokens: int, completion_tokens: int) -> tuple[float, bool]:
    """(cost_eur, uncosted) for a usage row. uncosted=True when the model has no
    rate yet (cost 0 but flagged so it shows up as unpriced, not free)."""
    r = _rate_for(model)
    if not r:
        return 0.0, True
    # TODO: (b)-light hook — H-weighted pricing multiplies the peg by a
    # harmonics-derived factor here. Blocked on harmonics rho>=0.7 calibration;
    # left as a clean seam, NOT wired (no harmonics coupling in v0).
    cost = (prompt_tokens * r["in"] + completion_tokens * r["out"]) / 1_000_000.0
    return round(cost, 8), False


# ─── Token estimation (when a provider omits usage) ─────────────────────────

def estimate_tokens(text: str) -> int:
    """Rough token count from text when the provider returns no usage object.
    ~4 chars/token is a coarse but serviceable heuristic for v0; rows estimated
    this way carry estimated=True so they're never mistaken for measured."""
    if not text:
        return 0
    return max(1, len(text) // 4)


# ─── Schema ─────────────────────────────────────────────────────────────────

COMPUTE_EVENTS_DDL = """
CREATE TABLE IF NOT EXISTS compute_events (
    id                SERIAL PRIMARY KEY,
    ts                TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    model             TEXT NOT NULL,
    prompt_tokens     INTEGER NOT NULL,
    completion_tokens INTEGER NOT NULL,
    estimated         BOOLEAN NOT NULL DEFAULT FALSE,
    est_cost_eur      NUMERIC(18, 8) NOT NULL DEFAULT 0,
    source            TEXT
);
CREATE INDEX IF NOT EXISTS compute_events_ts_idx ON compute_events (ts DESC);
CREATE INDEX IF NOT EXISTS compute_events_model_idx ON compute_events (model);
"""


def init_tables(conn=None) -> None:
    """Idempotent table create. Called from main.py startup hook (fail-soft)."""
    if not os.getenv("DATABASE_URL"):
        return
    try:
        owns_conn = conn is None
        if owns_conn:
            conn = psycopg2.connect(os.environ["DATABASE_URL"])
            conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(COMPUTE_EVENTS_DDL)
        if owns_conn:
            conn.close()
    except Exception as e:
        print(f"[compute_meter] table init skipped: {e}", flush=True)


# ─── Ledger (append-only) ────────────────────────────────────────────────────

def record_usage(
    *,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    estimated: bool = False,
    source: Optional[str] = None,
    conn=None,
) -> Optional[int]:
    """Append one immutable usage row. Returns the row id, or None if metering
    is unavailable. FAIL-SOFT by contract: metering must never break inference,
    so callers wrap this and any failure here is swallowed and logged."""
    if not os.getenv("DATABASE_URL"):
        return None
    pt = int(prompt_tokens or 0)
    ct = int(completion_tokens or 0)
    cost, uncosted = est_cost_eur(model, pt, ct)
    # A row is "estimated" if its tokens were estimated OR its model is uncosted.
    estimated = bool(estimated or uncosted)
    try:
        owns_conn = conn is None
        if owns_conn:
            conn = psycopg2.connect(os.environ["DATABASE_URL"])
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO compute_events
                        (model, prompt_tokens, completion_tokens, estimated,
                         est_cost_eur, source)
                       VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""",
                    (model, pt, ct, estimated, cost, source),
                )
                row = cur.fetchone()
            if owns_conn:
                conn.commit()
        finally:
            if owns_conn:
                conn.close()
        return row[0]
    except Exception as e:
        print(f"[compute_meter] record_usage skipped: {e}", flush=True)
        return None


def usage_from_response(client_type: str, raw) -> Optional[tuple[int, int]]:
    """Pull (prompt_tokens, completion_tokens) from a raw provider response,
    handling all three shapes _resolve() dispatches to. Returns None when the
    provider omitted usage (caller then estimates)."""
    try:
        if client_type == "anthropic":
            u = getattr(raw, "usage", None)
            if u is not None:
                return int(getattr(u, "input_tokens", 0)), int(getattr(u, "output_tokens", 0))
        elif client_type == "openai_compat":
            u = getattr(raw, "usage", None)
            if u is not None:
                return int(getattr(u, "prompt_tokens", 0)), int(getattr(u, "completion_tokens", 0))
        elif client_type == "ollama":
            # raw is the parsed JSON dict from /api/chat
            if isinstance(raw, dict) and ("prompt_eval_count" in raw or "eval_count" in raw):
                return int(raw.get("prompt_eval_count", 0)), int(raw.get("eval_count", 0))
    except Exception:
        pass
    return None


# ─── Derived-on-read readout ─────────────────────────────────────────────────

_WINDOWS = {"today", "7d", "30d", "all"}


def _cutoff_sql(window: str) -> str:
    """A SQL predicate on ts for the window. 'today' = since UTC midnight."""
    if window == "today":
        return "ts >= date_trunc('day', NOW() AT TIME ZONE 'UTC')"
    if window == "7d":
        return "ts >= NOW() - INTERVAL '7 days'"
    if window == "30d":
        return "ts >= NOW() - INTERVAL '30 days'"
    return "TRUE"  # all


def usage(window: str = "today") -> dict:
    """Totals (tokens + est_cost_eur) grouped by model, computed on read. No
    stored balance — this is the harmonics standing() pattern applied to compute."""
    if window not in _WINDOWS:
        raise HTTPException(status_code=400, detail=f"window must be one of {sorted(_WINDOWS)}")
    empty = {"window": window, "by_model": [], "totals": {
        "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0,
        "est_cost_eur": 0.0, "events": 0, "estimated_events": 0}}
    if not os.getenv("DATABASE_URL"):
        return empty
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    try:
        with conn.cursor() as cur:
            try:
                cur.execute(
                    f"""SELECT model,
                               SUM(prompt_tokens), SUM(completion_tokens),
                               SUM(est_cost_eur), COUNT(*),
                               SUM(CASE WHEN estimated THEN 1 ELSE 0 END)
                        FROM compute_events
                        WHERE {_cutoff_sql(window)}
                        GROUP BY model
                        ORDER BY SUM(est_cost_eur) DESC, SUM(completion_tokens) DESC""")
                rows = cur.fetchall()
            except psycopg2.errors.UndefinedTable:
                conn.rollback()
                rows = []
    finally:
        conn.close()
    by_model = []
    tp = tc = tcost = tev = test = 0
    for model, pt, ct, cost, ev, est in rows:
        pt, ct, cost, ev, est = int(pt or 0), int(ct or 0), float(cost or 0), int(ev or 0), int(est or 0)
        by_model.append({
            "model": model, "prompt_tokens": pt, "completion_tokens": ct,
            "total_tokens": pt + ct, "est_cost_eur": round(cost, 6),
            "events": ev, "estimated_events": est,
        })
        tp += pt; tc += ct; tcost += cost; tev += ev; test += est
    return {
        "window": window, "by_model": by_model,
        "totals": {
            "prompt_tokens": tp, "completion_tokens": tc, "total_tokens": tp + tc,
            "est_cost_eur": round(tcost, 6), "events": tev, "estimated_events": test,
        },
    }


# ─── HTTP endpoints ─────────────────────────────────────────────────────────

router = APIRouter()


@router.get("/meter/usage")
def get_usage(window: str = "today"):
    """Reconciled consumption totals + estimated cost, by model, for a window.
    Derived on read from the append-only ledger (today|7d|30d|all)."""
    try:
        return usage(window)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/meter/ledger")
def get_ledger(limit: int = 100):
    """Recent raw usage events, newest first. Read-only; rows are never updated
    or deleted (mirror of /harmonics/ledger)."""
    try:
        if not os.getenv("DATABASE_URL"):
            return {"events": [], "count": 0}
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        try:
            with conn.cursor() as cur:
                try:
                    cur.execute(
                        """SELECT id, ts, model, prompt_tokens, completion_tokens,
                                  estimated, est_cost_eur, source
                           FROM compute_events
                           ORDER BY ts DESC, id DESC LIMIT %s""",
                        (max(1, min(int(limit), 500)),),
                    )
                    rows = cur.fetchall()
                except psycopg2.errors.UndefinedTable:
                    conn.rollback()
                    rows = []
        finally:
            conn.close()
        events = [
            {
                "id": r[0], "ts": r[1].isoformat() if r[1] else None, "model": r[2],
                "prompt_tokens": r[3], "completion_tokens": r[4],
                "estimated": r[5], "est_cost_eur": float(r[6]) if r[6] is not None else 0.0,
                "source": r[7],
            }
            for r in rows
        ]
        return {"events": events, "count": len(events)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
