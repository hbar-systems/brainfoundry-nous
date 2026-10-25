"""
api/submissions.py — contribution submissions with review (2026-10-25).

People and agents submit a five-field contribution (hypothesis, prediction,
method, result, critique). The brain scores it first against a fixed rubric,
then the owner signs it (approve) before it becomes a Knowledge card. The
owner's review is itself a contribution the harmonics ledger records.

  POST /v1/submissions               public, rate-limited per IP
  GET  /v1/submissions?status=       owner (API key)
  POST /v1/submissions/{id}/decide   owner (API key)

Never money, never a balance: the only ledger touch is one harmonics event.
Generic: any brain can take submissions. See docs/public/contributions.md.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import threading
import time
import uuid
from typing import Any, Callable, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, Field

FIELDS = ("hypothesis", "prediction", "method", "result", "critique")
REQUIRED = ("hypothesis", "prediction", "method")
FIELD_MAX = 4000
SUBJECT = "contribution.submit"
HTTP_TIMEOUT = 6.0
TOP_K = 4

STATUSES = ("accepted", "quarantined", "scored", "awaiting_review", "approved", "rejected")

RUBRIC = """Score this contribution on a fixed rubric. Integers only.
- falsifiable: does the prediction name something that could prove the hypothesis wrong? 0 none, 1 vague, 2 testable, 3 sharp and quantitative or dated.
- method: could the method, as written, actually test the prediction? 0 no, 1 sketch, 2 reproducible in outline, 3 reproducible (steps, inputs, data named).
- critique: does the critique name a real weakness of the work itself? 0 absent or empty, 1 token, 2 honest and specific.
- relevance: does it bear on the reference passages from this brain's own corpus? 0 unrelated, 1 adjacent, 2 directly relevant. With no passages, give 0.
Return ONLY one JSON object: {"falsifiable": n, "method": n, "critique": n, "relevance": n, "note": "two sentences"}"""

_LIMITS = {"falsifiable": 3, "method": 3, "critique": 2, "relevance": 2}


# ─── Store ──────────────────────────────────────────────────────────────────

DDL = """
CREATE TABLE IF NOT EXISTS submissions (
    id            TEXT PRIMARY KEY,
    created_at    BIGINT NOT NULL,
    title         TEXT NOT NULL,
    kind          TEXT NOT NULL,
    contact       TEXT,
    fields        TEXT NOT NULL,            -- JSON, untrusted text
    issuer        TEXT,                     -- verified issuer brain_id (agents)
    status        TEXT NOT NULL,
    scan          TEXT,                     -- JSON injection scan, worst field
    score         INTEGER,
    breakdown     TEXT,
    note          TEXT,
    retrieved     TEXT,                     -- JSON list: chunks the scorer saw
    decision      TEXT,
    decision_note TEXT,
    decided_at    BIGINT,
    doc_name      TEXT,
    event_id      INTEGER
);
"""
_COLS = ("id", "created_at", "title", "kind", "contact", "fields", "issuer", "status", "scan",
         "score", "breakdown", "note", "retrieved", "decision", "decision_note", "decided_at",
         "doc_name", "event_id")
_JSON_COLS = ("fields", "scan", "breakdown", "retrieved")


class MemStore:
    """In-process store (tests, and the interface PgStore follows)."""

    def __init__(self):
        self.rows: Dict[str, Dict[str, Any]] = {}

    def insert(self, rec: Dict[str, Any]) -> None:
        self.rows[rec["id"]] = dict(rec)

    def get(self, sid: str) -> Optional[Dict[str, Any]]:
        r = self.rows.get(sid)
        return dict(r) if r else None

    def list(self, status: Optional[str], limit: int) -> List[Dict[str, Any]]:
        rows = [dict(r) for r in self.rows.values() if not status or r["status"] == status]
        return sorted(rows, key=lambda r: -r["created_at"])[:limit]

    def update(self, sid: str, **kw) -> None:
        self.rows[sid].update(kw)


class PgStore:
    def _conn(self):
        import psycopg2
        if not os.getenv("DATABASE_URL"):
            raise RuntimeError("DATABASE_URL not configured")
        return psycopg2.connect(os.environ["DATABASE_URL"])

    @staticmethod
    def _row(vals) -> Dict[str, Any]:
        rec = dict(zip(_COLS, vals))
        for c in _JSON_COLS:
            if rec.get(c) is not None:
                rec[c] = json.loads(rec[c])
        return rec

    def insert(self, rec: Dict[str, Any]) -> None:
        vals = [json.dumps(rec.get(c)) if c in _JSON_COLS and rec.get(c) is not None else rec.get(c)
                for c in _COLS]
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(f"INSERT INTO submissions ({','.join(_COLS)}) VALUES ({','.join(['%s'] * len(_COLS))})", vals)
            conn.commit()
        finally:
            conn.close()

    def get(self, sid: str) -> Optional[Dict[str, Any]]:
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(f"SELECT {','.join(_COLS)} FROM submissions WHERE id=%s", (sid,))
                row = cur.fetchone()
        finally:
            conn.close()
        return self._row(row) if row else None

    def list(self, status: Optional[str], limit: int) -> List[Dict[str, Any]]:
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                if status:
                    cur.execute(f"SELECT {','.join(_COLS)} FROM submissions WHERE status=%s ORDER BY created_at DESC LIMIT %s", (status, limit))
                else:
                    cur.execute(f"SELECT {','.join(_COLS)} FROM submissions ORDER BY created_at DESC LIMIT %s", (limit,))
                rows = cur.fetchall()
        finally:
            conn.close()
        return [self._row(r) for r in rows]

    def update(self, sid: str, **kw) -> None:
        sets = ",".join(f"{k}=%s" for k in kw)
        vals = [json.dumps(v) if k in _JSON_COLS and v is not None else v for k, v in kw.items()]
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(f"UPDATE submissions SET {sets} WHERE id=%s", (*vals, sid))
            conn.commit()
        finally:
            conn.close()


_store: Any = None


def get_store():
    global _store
    if _store is None:
        _store = PgStore()
    return _store


def set_store(store) -> None:
    global _store
    _store = store


def init_tables(conn=None) -> None:
    """Idempotent table create. Called from the main.py startup hook (fail-soft)."""
    if not os.getenv("DATABASE_URL"):
        return
    try:
        import psycopg2
        owns = conn is None
        if owns:
            conn = psycopg2.connect(os.environ["DATABASE_URL"])
            conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(DDL)
        if owns:
            conn.close()
    except Exception as e:
        print(f"[submissions] table init skipped: {e}", flush=True)


# ─── Rate limit: small in-memory, per IP ────────────────────────────────────

class IPLimiter:
    def __init__(self):
        self.hits: Dict[str, List[float]] = {}
        self.lock = threading.Lock()

    def allow(self, ip: str, now: Optional[float] = None) -> bool:
        maxn = int(os.getenv("SUBMISSIONS_RATE_MAX", "5"))
        window = float(os.getenv("SUBMISSIONS_RATE_WINDOW", "3600"))
        now = time.time() if now is None else now
        with self.lock:
            hits = [t for t in self.hits.get(ip, []) if now - t < window]
            if len(hits) >= maxn:
                self.hits[ip] = hits
                return False
            hits.append(now)
            self.hits[ip] = hits
            return True


_limiter = IPLimiter()


# ─── Agent assertion ────────────────────────────────────────────────────────

def _b64_claims(token: str) -> Dict[str, Any]:
    import base64
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("invalid_token_format")
    seg = parts[1]
    return json.loads(base64.urlsafe_b64decode(seg + "=" * (-len(seg) % 4)).decode())


def _is_public_host(host: str) -> bool:
    from api.tools.fetch_url import _is_public_address
    return _is_public_address(host)


def _http_get(url: str):
    import httpx
    return httpx.get(url, timeout=HTTP_TIMEOUT, follow_redirects=False)


def verify_agent_assertion(token: str) -> str:
    """Verify an agent's assertion; return the issuer brain_id.

    Same shape as the radio code: aud is this brain's BRAIN_ID, the issuer's
    public key comes from its own GET /identity (https, public host only), the
    claimed iss must equal the brain_id that /identity publishes. Raises
    ValueError with a short reason.
    """
    from urllib.parse import urlparse
    from api.identity.core import verify_federation_assertion
    from api.identity import replay_cache

    this_brain = os.getenv("BRAIN_ID")
    if not this_brain:
        raise ValueError("BRAIN_ID not configured")
    claims = _b64_claims(token)
    endpoint = str(claims.get("issuer_endpoint") or "").strip().rstrip("/")
    p = urlparse(endpoint)
    if p.scheme != "https" or not p.hostname or p.username or p.password:
        raise ValueError("issuer_endpoint must be a public https URL")
    if not _is_public_host(p.hostname):
        raise ValueError("issuer_endpoint is not a public address")
    r = _http_get(f"{endpoint}/identity")
    if r.status_code != 200:
        raise ValueError(f"issuer /identity answered {r.status_code}")
    ident = r.json()
    pub, bid = ident.get("public_key"), ident.get("brain_id")
    if not pub or not bid:
        raise ValueError("issuer /identity lacks public_key or brain_id")
    verified = verify_federation_assertion(
        public_key_b64=pub, token=token, expected_audience=this_brain, expected_issuer=bid)
    if verified.get("sub") != SUBJECT:
        raise ValueError("sub_mismatch")
    jti = verified.get("jti")
    if not jti:
        raise ValueError("missing_jti")
    if replay_cache.seen_before(jti):
        raise ValueError("replay_detected")
    replay_cache.record(jti, exp=verified["exp"])
    return str(bid)


# ─── Scoring ────────────────────────────────────────────────────────────────

def contribution_text(title: str, fields: Dict[str, str]) -> str:
    return "\n\n".join([title] + [f"{k}: {fields.get(k, '')}" for k in FIELDS if fields.get(k)])


def build_score_prompt(title: str, fields: Dict[str, str], passages: List[str]) -> str:
    """The reasoner sees the title, the five fields and the corpus passages. Never the contact."""
    from api.security import untrusted as U
    sub = contribution_text(title, fields)
    ref = "\n\n".join(f"[{i + 1}] {p}" for i, p in enumerate(passages)) or "(no passages found)"
    return (
        U.with_policy_preamble("You are a strict reviewer. Score a submission against a fixed rubric.")
        + "\n\n" + RUBRIC
        + "\n\n" + U.untrusted_context_block("reference passages from this brain's corpus", ref)
        + "\n\n" + U.untrusted_context_block("submission under review", sub)
        + "\n\nJSON:"
    )


def parse_score(raw: str) -> Optional[Dict[str, Any]]:
    m = re.search(r"\{.*\}", raw or "", re.DOTALL)
    if not m:
        return None
    try:
        d = json.loads(m.group(0))
        parts = {}
        for k, cap in _LIMITS.items():
            parts[k] = max(0, min(cap, int(d.get(k))))
    except Exception:
        return None
    note = re.sub(r"\s+", " ", str(d.get("note") or "")).strip()[:500]
    return {"total": sum(parts.values()), "breakdown": parts, "note": note}


def _search(query: str) -> List[Dict[str, Any]]:
    from api import main as m
    return m.search_similar_documents(query, limit=TOP_K, allow_local_only=False)


async def _complete(prompt: str) -> str:
    from api import providers
    model = os.getenv("SUBMISSIONS_SCORER_MODEL") or providers.default_model()
    return await providers.complete(model, [{"role": "user", "content": prompt}], max_tokens=600)


async def score_submission(sid: str) -> None:
    """Score one accepted submission. No reasoner or an unusable answer -> awaiting_review."""
    store = get_store()
    rec = store.get(sid)
    if not rec or rec["status"] != "accepted":
        return
    text = contribution_text(rec["title"], rec["fields"])
    try:
        docs = await asyncio.to_thread(_search, text)
    except Exception:
        docs = []
    passages = [str(d.get("content") or "")[:1200] for d in docs if d.get("content")]
    store.update(sid, retrieved=passages)
    try:
        raw = await _complete(build_score_prompt(rec["title"], rec["fields"], passages))
        parsed = parse_score(raw)
    except Exception as e:
        print(f"[submissions] scorer unavailable for {sid}: {type(e).__name__}", flush=True)
        parsed = None
    if parsed is None:
        store.update(sid, status="awaiting_review", score=None)
        return
    store.update(sid, status="scored", score=parsed["total"], breakdown=parsed["breakdown"], note=parsed["note"])


# ─── Approve: card + one harmonics event ────────────────────────────────────

def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:50] or "submission"


def render_card(rec: Dict[str, Any], owner_note: str) -> str:
    f = rec["fields"]
    lines = [
        "---", "tags: submission", f"provenance: submission {rec['id']}", f"kind: {rec['kind']}",
        f"score: {rec['score'] if rec['score'] is not None else 'unscored'}/10", "---", "",
        f"# {rec['title']}", "",
    ]
    for k in FIELDS:
        if f.get(k):
            lines += [f"## {k.capitalize()}", "", f[k], ""]
    lines += ["## Review", "", f"Score: {rec['score'] if rec['score'] is not None else 'unscored'} of 10"]
    if rec.get("note"):
        lines.append(f"Scorer note: {rec['note']}")
    if owner_note:
        lines.append(f"Owner note: {owner_note}")
    return "\n".join(lines) + "\n"


def _ingest(name: str, text: str, injection_risk: Optional[str]) -> int:
    """Through the normal ingest path (the same generator POST /documents/upload runs on approval).
    The owner's approve is the human approval; raises on failure."""
    from api import main as m
    events = list(m._stream_ingest_path_b(
        text=text, filename=name, content_type="text/markdown", size=len(text.encode("utf-8")),
        proposal_id=f"submission-{name}", layer="submission", injection_risk=injection_risk))
    if any(e.startswith("event: error") for e in events):
        raise RuntimeError("ingest failed")
    return len(events)


def _record_harmonics(c: str, r: str, peer: str) -> Dict[str, Any]:
    from api import harmonics as h
    cos, sin, score = h.coherence(c, r)
    eid = h.record_event(peer_pubkey=peer, role="receiver", cos=cos, sin=sin, score=score,
                         content_hash=h.content_hash(c, r), event_timestamp=int(time.time()))
    return {"id": eid, "cos": cos, "sin": sin, "score": score}


def _audit(entry: Dict[str, Any]) -> None:
    from api.tools import federation_audit
    federation_audit.log({"surface": "submissions", **entry})


# ─── Routes ─────────────────────────────────────────────────────────────────

class SubmitFields(BaseModel):
    hypothesis: str = Field("", max_length=FIELD_MAX)
    prediction: str = Field("", max_length=FIELD_MAX)
    method: str = Field("", max_length=FIELD_MAX)
    result: str = Field("", max_length=FIELD_MAX)
    critique: str = Field("", max_length=FIELD_MAX)


class SubmitRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    kind: str
    contact: Optional[str] = Field(None, max_length=200)
    fields: SubmitFields
    assertion: Optional[str] = Field(None, max_length=8000)


class DecideRequest(BaseModel):
    decision: str
    note: str = Field("", max_length=2000)


def _client_ip(request: Request) -> str:
    try:
        from api import main as m
        return m._public_client_ip(request)
    except Exception:
        return request.client.host if request.client else "unknown"


def _public_view(rec: Dict[str, Any], full: bool = False) -> Dict[str, Any]:
    keys = ["id", "created_at", "title", "kind", "status", "score", "breakdown", "note", "issuer",
            "decision", "decision_note", "decided_at", "doc_name", "event_id"]
    out = {k: rec.get(k) for k in keys}
    if full:
        out.update(fields=rec["fields"], contact=rec.get("contact"), scan=rec.get("scan"))
    return out


def build_router(get_api_key: Callable) -> APIRouter:
    router = APIRouter()

    @router.post("/v1/submissions")
    async def submit(req: SubmitRequest, request: Request, background: BackgroundTasks):
        if not _limiter.allow(_client_ip(request)):
            raise HTTPException(429, "rate_limited: 5 submissions per hour")
        if req.kind not in ("human", "agent"):
            raise HTTPException(422, "kind must be human or agent")
        fields = {k: (getattr(req.fields, k) or "").strip() for k in FIELDS}
        missing = [k for k in REQUIRED if not fields[k]]
        if missing:
            raise HTTPException(422, f"required fields empty: {', '.join(missing)}")
        issuer = None
        if req.kind == "agent":
            if not req.assertion:
                raise HTTPException(401, "assertion required for kind agent")
            try:
                issuer = await asyncio.to_thread(verify_agent_assertion, req.assertion)
            except ValueError as e:
                raise HTTPException(401, f"assertion_verify_failed: {e}"[:200])
            except Exception as e:
                raise HTTPException(502, f"issuer unreachable: {type(e).__name__}")
        from api import injection_scan
        worst = {"risk": "none", "score": 0, "signals": [], "summary": ""}
        rank = {"none": 0, "low": 1, "medium": 2, "high": 3}
        for text in [req.title, req.contact or "", *fields.values()]:
            s = injection_scan.scan_text(text)
            if rank[s["risk"]] > rank[worst["risk"]] or (s["risk"] == worst["risk"] and s["score"] > worst["score"]):
                worst = s
        sid = uuid.uuid4().hex[:12]
        status = "quarantined" if worst["risk"] == "high" else "accepted"
        get_store().insert({
            "id": sid, "created_at": int(time.time()), "title": req.title.strip(), "kind": req.kind,
            "contact": (req.contact or "").strip() or None, "fields": fields, "issuer": issuer,
            "status": status, "scan": worst, "score": None, "breakdown": None, "note": None,
            "retrieved": None, "decision": None, "decision_note": None, "decided_at": None,
            "doc_name": None, "event_id": None,
        })
        if status == "accepted":
            background.add_task(score_submission, sid)
        return {"id": sid, "status": status}

    @router.get("/v1/submissions")
    def list_submissions(status: Optional[str] = None, limit: int = 100, _k: str = Depends(get_api_key)):
        if status and status not in STATUSES:
            raise HTTPException(422, f"status must be one of {', '.join(STATUSES)}")
        rows = get_store().list(status, max(1, min(int(limit), 500)))
        return {"submissions": [_public_view(r, full=True) for r in rows]}

    @router.post("/v1/submissions/{sid}/decide")
    def decide(sid: str, req: DecideRequest, _k: str = Depends(get_api_key)):
        if req.decision not in ("approve", "reject"):
            raise HTTPException(422, "decision must be approve or reject")
        store = get_store()
        rec = store.get(sid)
        if not rec:
            raise HTTPException(404, "no such submission")
        if rec["status"] in ("approved", "rejected"):
            raise HTTPException(409, f"already {rec['status']}")
        now = int(time.time())
        if req.decision == "reject":
            store.update(sid, status="rejected", decision="reject", decision_note=req.note, decided_at=now)
            _audit({"direction": "in", "outcome": "decide:reject", "submission": sid, "peer_brain_id": rec.get("issuer") or "human"})
            return {"id": sid, "status": "rejected"}
        risk = (rec.get("scan") or {}).get("risk")
        name = f"submissions/{sid}-{_slug(rec['title'])}.md"
        card = render_card(rec, req.note)
        try:
            _ingest(name, card, risk)
        except Exception as e:
            raise HTTPException(502, f"ingest failed: {type(e).__name__}")
        c = contribution_text(rec["title"], rec["fields"])
        r = "\n\n".join(rec.get("retrieved") or [])
        peer = rec.get("issuer") or f"human:{sid}"
        event, reason = None, ""
        if not r:
            reason = "no corpus passages: nothing for the contribution to land against"
        else:
            try:
                event = _record_harmonics(c, r, peer)
            except Exception as e:
                reason = f"{type(e).__name__}: {e}"[:200]
        store.update(sid, status="approved", decision="approve", decision_note=req.note,
                     decided_at=now, doc_name=name, event_id=(event or {}).get("id"))
        _audit({"direction": "in", "outcome": "decide:approve", "submission": sid, "peer_brain_id": peer,
                "document": name, "harmonics_event": (event or {}).get("id")})
        out = {"id": sid, "status": "approved", "document": name, "event": event}
        if event is None:
            out["event_reason"] = reason
        return out

    return router
