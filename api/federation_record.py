"""
api/federation_record.py: the record door (A2A-2, 2026-11-23).

A pinned peer brain hands this brain a signed JSON record of any kind; this brain
checks it, keeps it, and countersigns its hash with a receipt. The owner then
confirms (or declines) it with a press in the console; the confirmation is itself a
signed record that goes back to the sender's brain through the same door, where it
is kept and countersigned in turn. Both brains end up holding the same rows.

The door knows nothing about what a record means. `kind` and `body` are opaque here:
an application on top (an operator's own tooling) gives them
meaning. Nothing about what is exchanged lives in this file.

Trust, the same rules as the ask door (api/ask.py):
  - the sender must be a pinned peer (data/peers.json or known_peers.toml); a key
    inside a message never counts, and /identity is never fetched here;
  - the signature is ED25519 over RFC 8785 bytes (api/federation_jcs.py), floats refused;
  - the record must be addressed to this brain and not expired; lifetimes are capped;
  - replay: (from, rid) is kept for good. The same record again returns the same
    receipt; the same rid with other content is refused.

Signed shapes (all integers, no floats):
  record  {v, kind, rid, from, to, iat, exp, body, [ref], [confirm]}
  receipt {v, kind:"record.receipt", rid, from, record_hash, by, at}
  wire    POST /v1/federation/record  {"record": record, "sig": b64url}
          -> 200 {"receipt": receipt, "sig": b64url}

`confirm` is the exact text the receiving owner types to confirm (default "confirm").
A confirmation is a record of kind "record.confirm" (or "record.decline") with
rid "<rid>.confirm", ref = the confirmed record's hash, body {rid, kind, note}.

Store: append-only JSONL, hash-chained, mode 600 (FEDERATION_RECORDS_PATH,
default data/records.jsonl). See docs/RECORDS.md.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from api.federation_jcs import canonicalize

RECORD_PATH = "/v1/federation/record"
VERSION = 1
KIND_RE = re.compile(r"^[a-z][a-z0-9._-]{0,63}$")
RID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,119}$")
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
MAX_BODY_BYTES = 16_000
MAX_CONFIRM = 200
MAX_NOTE = 500
MAX_TTL = 30 * 24 * 3600
CLOCK_SKEW = 300
DEFAULT_TTL = 7 * 24 * 3600
GENESIS = "0" * 64
RESERVED = ("record.receipt",)
REPLY_KINDS = ("record.confirm", "record.decline")
HELP_PREFIX = "help."  # help.request / help.answer: api/federation_help.py checks their shape
RECORD_FIELDS = {"v", "kind", "rid", "from", "to", "iat", "exp", "body", "ref", "confirm"}


class RecordError(Exception):
    """A refusal: HTTP status and a short reason, safe to show."""

    def __init__(self, status: int, reason: str):
        super().__init__(reason)
        self.status = status
        self.reason = reason


# ---------------------------------------------------------------- bytes and keys

def _no_floats(x: Any) -> None:
    if isinstance(x, float):
        raise RecordError(400, "float in a signed record (use integers)")
    if isinstance(x, dict):
        for k, v in x.items():
            if not isinstance(k, str):
                raise RecordError(400, "non-string key")
            _no_floats(v)
    elif isinstance(x, list):
        for v in x:
            _no_floats(v)
    elif not (x is None or isinstance(x, (str, int, bool))):
        raise RecordError(400, f"unsupported value {type(x).__name__}")


def canonical(doc: Dict[str, Any]) -> bytes:
    _no_floats(doc)
    return canonicalize(doc)


def record_hash(doc: Dict[str, Any]) -> str:
    return hashlib.sha256(canonical(doc)).hexdigest()


def _b64e(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def public_key_of(private_key_b64: str) -> str:
    sk = Ed25519PrivateKey.from_private_bytes(_b64d(private_key_b64))
    return _b64e(sk.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw))


def sign_doc(private_key_b64: str, doc: Dict[str, Any]) -> str:
    return _b64e(Ed25519PrivateKey.from_private_bytes(_b64d(private_key_b64)).sign(canonical(doc)))


def verify_doc(public_key_b64: str, sig_b64: str, doc: Dict[str, Any]) -> bool:
    try:
        Ed25519PublicKey.from_public_bytes(_b64d(public_key_b64)).verify(_b64d(sig_b64), canonical(doc))
        return True
    except Exception:
        return False


def iso(t: float) -> str:
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------- shapes

def make_record(*, kind: str, rid: str, frm: str, to: str, body: Dict[str, Any], now: int,
                ttl: int = DEFAULT_TTL, ref: Optional[str] = None,
                confirm: Optional[str] = None) -> Dict[str, Any]:
    rec: Dict[str, Any] = {"v": VERSION, "kind": kind, "rid": rid, "from": frm, "to": to,
                           "iat": int(now), "exp": int(now) + int(ttl), "body": body}
    if ref is not None:
        rec["ref"] = ref
    if confirm is not None:
        rec["confirm"] = confirm
    check_shape(rec, now=int(now))
    return rec


def make_receipt(rec: Dict[str, Any], *, by: str, now: int) -> Dict[str, Any]:
    return {"v": VERSION, "kind": "record.receipt", "rid": rec["rid"], "from": rec["from"],
            "record_hash": record_hash(rec), "by": by, "at": iso(now)}


def confirm_text(rec: Dict[str, Any]) -> str:
    c = rec.get("confirm")
    return c if isinstance(c, str) and c else "confirm"


def check_shape(rec: Any, *, now: int) -> None:
    """Everything about a record that needs no key and no store."""
    if not isinstance(rec, dict):
        raise RecordError(400, "record must be an object")
    extra = set(rec) - RECORD_FIELDS
    if extra:
        raise RecordError(400, f"unknown fields: {sorted(extra)}")
    if rec.get("v") != VERSION:
        raise RecordError(400, "wrong version")
    kind = rec.get("kind")
    if not isinstance(kind, str) or not KIND_RE.match(kind) or kind in RESERVED:
        raise RecordError(400, "bad kind")
    if not isinstance(rec.get("rid"), str) or not RID_RE.match(rec["rid"]):
        raise RecordError(400, "bad rid (8..120 of A-Z a-z 0-9 . _ : -)")
    for f in ("from", "to"):
        if not isinstance(rec.get(f), str) or not ID_RE.match(rec[f]):
            raise RecordError(400, f"bad {f}")
    iat, exp = rec.get("iat"), rec.get("exp")
    for v in (iat, exp):
        if not isinstance(v, int) or isinstance(v, bool):
            raise RecordError(400, "iat and exp must be integers")
    if iat > now + CLOCK_SKEW:
        raise RecordError(400, "issued in the future")
    if exp <= now:
        raise RecordError(400, "expired")
    if exp - iat > MAX_TTL:
        raise RecordError(400, f"lifetime above {MAX_TTL}s")
    body = rec.get("body")
    if not isinstance(body, dict):
        raise RecordError(400, "body must be an object")
    if len(canonical(body)) > MAX_BODY_BYTES:
        raise RecordError(413, f"body above {MAX_BODY_BYTES} bytes")
    ref = rec.get("ref")
    if ref is not None and (not isinstance(ref, str) or not re.fullmatch(r"[0-9a-f]{64}", ref)):
        raise RecordError(400, "ref must be a sha256 hex")
    c = rec.get("confirm")
    if c is not None and (not isinstance(c, str) or not c.strip() or len(c) > MAX_CONFIRM):
        raise RecordError(400, f"confirm must be 1..{MAX_CONFIRM} characters")
    if kind in REPLY_KINDS:
        if ref is None or not isinstance(body.get("rid"), str):
            raise RecordError(400, "a confirmation needs ref and body.rid")
    if kind.startswith(HELP_PREFIX):  # MEMBERS-14: help records have one fixed shape each
        from api.federation_help import check_body
        check_body(kind, body, ref)


# ---------------------------------------------------------------- store

class Store:
    """Append-only JSONL, hash-chained, one per brain. Rows are keyed '<from>/<rid>'."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._lock = threading.RLock()

    def lines(self) -> List[Dict[str, Any]]:
        if not self.path.exists():
            return []
        return [json.loads(l) for l in self.path.read_text(encoding="utf-8").splitlines() if l.strip()]

    def append(self, event: str, key: str, body: Dict[str, Any], now: float) -> Dict[str, Any]:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            ls = self.lines()
            prev = ls[-1]["hash"] if ls else GENESIS
            entry = {"seq": len(ls), "at": iso(now), "event": event, "key": key, "body": body, "prev": prev}
            entry["hash"] = hashlib.sha256(canonical(entry)).hexdigest()
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            with os.fdopen(fd, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, sort_keys=True, ensure_ascii=False) + "\n")
            return entry

    def chain_ok(self) -> bool:
        prev = GENESIS
        for i, e in enumerate(self.lines()):
            core = {k: v for k, v in e.items() if k != "hash"}
            if e.get("seq") != i or e.get("prev") != prev or hashlib.sha256(canonical(core)).hexdigest() != e.get("hash"):
                return False
            prev = e["hash"]
        return True

    def state(self) -> Dict[str, Dict[str, Any]]:
        out: Dict[str, Dict[str, Any]] = {}
        for e in self.lines():
            s = out.setdefault(e["key"], {"key": e["key"], "events": []})
            s["events"].append(e["event"])
            s.update(e["body"])
        return out


def default_store() -> Store:
    return Store(Path(os.getenv("FEDERATION_RECORDS_PATH", "data/records.jsonl")))


# ---------------------------------------------------------------- the door

PinLookup = Callable[[str], Optional[Dict[str, Any]]]
# deliver(peer, envelope) -> (http_status, reply_json); peer has brain_id, endpoint, public_key
Deliver = Callable[[Dict[str, Any], Dict[str, Any]], Tuple[int, Dict[str, Any]]]


class Door:
    """One brain's record door: its id and key, its pins, its store, a way to reach peers."""

    def __init__(self, *, brain_id: str, private_key: str, store: Store, pins: PinLookup,
                 deliver: Optional[Deliver] = None, clock: Callable[[], float] = time.time):
        self.id = brain_id
        self._key = private_key
        self.pub = public_key_of(private_key)
        self.store = store
        self.pins = pins
        self.deliver = deliver
        self.clock = clock

    def _now(self) -> int:
        return int(self.clock())

    def _pin(self, brain_id: str) -> Dict[str, Any]:
        p = self.pins(brain_id) if brain_id else None
        if not p or not p.get("public_key"):
            raise RecordError(403, "unknown_peer")
        return p

    # -- inbound: any pinned peer
    def receive(self, envelope: Any) -> Dict[str, Any]:
        if not isinstance(envelope, dict):
            raise RecordError(400, "envelope must be an object")
        rec, sig = envelope.get("record"), envelope.get("sig")
        if not isinstance(rec, dict) or not isinstance(sig, str):
            raise RecordError(400, "envelope needs record and sig")
        frm = rec.get("from")
        peer = self._pin(frm if isinstance(frm, str) else "")
        if not verify_doc(peer["public_key"], sig, rec):
            raise RecordError(401, "bad signature against the pinned key")
        if rec.get("to") != self.id:
            raise RecordError(403, "not addressed to this brain")
        key = f"{frm}/{rec.get('rid')}"
        with self.store._lock:
            seen = self.store.state().get(key)
            if seen and "in" in seen["events"]:
                if record_hash(seen["record"]) == record_hash(rec):
                    return {"receipt": seen["receipt"], "sig": seen["receipt_sig"]}  # replay: same receipt
                raise RecordError(409, "rid already used with other content")
            now = self._now()
            check_shape(rec, now=now)
            if rec["kind"] in REPLY_KINDS:
                self._check_reply(rec)
            elif rec["kind"].startswith(HELP_PREFIX):
                from api.federation_help import check_inbound
                check_inbound(self, rec)
            receipt = make_receipt(rec, by=self.id, now=now)
            rsig = sign_doc(self._key, receipt)
            self.store.append("in", key, {"dir": "in", "record": rec, "sig": sig,
                                          "receipt": receipt, "receipt_sig": rsig}, now)
            return {"receipt": receipt, "sig": rsig}

    def _check_reply(self, rec: Dict[str, Any]) -> None:
        """A confirm/decline must answer a record this brain sent to that peer."""
        orig = self.store.state().get(f"{self.id}/{rec['body']['rid']}")
        if not orig or orig.get("dir") != "out" or orig["record"]["to"] != rec["from"]:
            raise RecordError(404, "confirms no record this brain sent to you")
        if record_hash(orig["record"]) != rec["ref"]:
            raise RecordError(409, "ref does not match the record sent")

    # -- outbound: the owner (route needs the API key)
    def send(self, *, kind: str, to: str, body: Dict[str, Any], rid: str,
             ref: Optional[str] = None, confirm: Optional[str] = None,
             ttl: int = DEFAULT_TTL) -> Dict[str, Any]:
        self._pin(to)
        if kind in REPLY_KINDS:
            raise RecordError(400, "confirmations come from the confirm press")
        key = f"{self.id}/{rid}"
        if key in self.store.state():
            raise RecordError(409, "rid already used")
        rec = make_record(kind=kind, rid=rid, frm=self.id, to=to, body=body, now=self._now(),
                          ttl=ttl, ref=ref, confirm=confirm)
        return self._sign_and_deliver(key, rec)

    def _sign_and_deliver(self, key: str, rec: Dict[str, Any]) -> Dict[str, Any]:
        sig = sign_doc(self._key, rec)
        self.store.append("out", key, {"dir": "out", "record": rec, "sig": sig}, self._now())
        return self.redeliver(rec["rid"])

    def redeliver(self, rid: str) -> Dict[str, Any]:
        """Deliver a signed outbound record (again). The peer is idempotent on it."""
        key = f"{self.id}/{rid}"
        s = self.store.state().get(key)
        if not s or s.get("dir") != "out":
            raise RecordError(404, "no such outbound record")
        if "receipt" in s:
            return self.row(key)
        if self.deliver is None:
            return dict(self.row(key), delivery="pending: no way to reach peers")
        peer = self._pin(s["record"]["to"])
        try:
            status, reply = self.deliver(peer, {"record": s["record"], "sig": s["sig"]})
        except Exception as e:
            status, reply = 0, {"detail": f"unreachable: {type(e).__name__}"}
        if status != 200:
            reason = str((reply or {}).get("detail") or (reply or {}).get("error") or f"HTTP {status}")[:200]
            self.store.append("undelivered", key, {"last_error": reason}, self._now())
            return dict(self.row(key), delivery=f"pending: {reason}")
        receipt, rsig = (reply or {}).get("receipt"), (reply or {}).get("sig")
        want = {"v": VERSION, "kind": "record.receipt", "rid": rid, "from": self.id,
                "record_hash": record_hash(s["record"]), "by": s["record"]["to"]}
        if (not isinstance(receipt, dict) or not isinstance(rsig, str)
                or {k: receipt.get(k) for k in want} != want or set(receipt) != set(want) | {"at"}):
            self.store.append("undelivered", key, {"last_error": "receipt does not match"}, self._now())
            raise RecordError(502, "peer receipt does not match the record")
        if not verify_doc(peer["public_key"], rsig, receipt):
            self.store.append("undelivered", key, {"last_error": "receipt signature"}, self._now())
            raise RecordError(502, "peer receipt signature does not verify against the pin")
        self.store.append("receipted", key, {"receipt": receipt, "receipt_sig": rsig}, self._now())
        return self.row(key)

    # -- the owner's press on an inbound record
    def answer(self, *, frm: str, rid: str, typed: str, decline: bool = False, note: str = "") -> Dict[str, Any]:
        key = f"{frm}/{rid}"
        s = self.store.state().get(key)
        if not s or s.get("dir") != "in":
            raise RecordError(404, "no such inbound record")
        if s["record"]["kind"] in REPLY_KINDS:
            raise RecordError(400, "a confirmation is not confirmed again")
        if s["record"]["kind"].startswith(HELP_PREFIX):
            raise RecordError(400, "help is answered in Federation, Help")
        if s.get("answer"):
            return self.row(f"{self.id}/{s['answer']}")
        want = "decline" if decline else confirm_text(s["record"])
        if typed != want:
            raise RecordError(400, f"type exactly: {want}")
        note = (note or "").strip()
        if len(note) > MAX_NOTE:
            raise RecordError(400, f"note above {MAX_NOTE} characters")
        arid = f"{rid}.{'decline' if decline else 'confirm'}"[:120]
        kind = "record.decline" if decline else "record.confirm"
        rec = make_record(kind=kind, rid=arid, frm=self.id, to=frm, now=self._now(),
                          ref=record_hash(s["record"]),
                          body={"rid": rid, "kind": s["record"]["kind"], "note": note})
        self.store.append("answered", key, {"answer": arid}, self._now())
        return self._sign_and_deliver(f"{self.id}/{arid}", rec)

    # -- views
    def row(self, key: str) -> Dict[str, Any]:
        """The part both brains hold identically: record, its sig, the receipt, its sig."""
        s = self.store.state().get(key)
        if not s:
            raise RecordError(404, "no such record")
        return {k: s[k] for k in ("record", "sig", "receipt", "receipt_sig") if k in s}

    def list(self) -> List[Dict[str, Any]]:
        st = self.store.state()
        out = []
        for key, s in st.items():
            r = s["record"]
            replies = [x for x in st.values() if x["record"].get("ref") == record_hash(r)
                       and x["record"]["kind"] in REPLY_KINDS]
            out.append({
                "key": key, "dir": s["dir"], "kind": r["kind"], "rid": r["rid"], "from": r["from"],
                "to": r["to"], "body": r["body"], "confirm_text": confirm_text(r),
                "receipted": "receipt" in s, "last_error": s.get("last_error") if "receipt" not in s else None,
                "answer": (replies[0]["record"]["kind"].split(".")[1] if replies else None),
                "answerable": (s["dir"] == "in" and r["kind"] not in REPLY_KINDS
                               and not r["kind"].startswith(HELP_PREFIX) and not s.get("answer")),
                "at": s["receipt"]["at"] if "receipt" in s else None,
            })
        return out

    def verify(self) -> List[str]:
        problems = [] if self.store.chain_ok() else ["hash chain broken"]
        for key, s in self.store.state().items():
            r = s["record"]
            fk = self.pub if r["from"] == self.id else (self.pins(r["from"]) or {}).get("public_key")
            tk = self.pub if r["to"] == self.id else (self.pins(r["to"]) or {}).get("public_key")
            if not fk or not verify_doc(fk, s["sig"], r):
                problems.append(f"{key}: record signature")
            if "receipt" in s and (not tk or not verify_doc(tk, s["receipt_sig"], s["receipt"])
                                   or s["receipt"]["record_hash"] != record_hash(r)):
                problems.append(f"{key}: receipt")
        return problems


# ---------------------------------------------------------------- wiring helpers (main.py)

def pinned_peer(brain_id: str) -> Optional[Dict[str, Any]]:
    from api.ask import find_pinned_peer
    return find_pinned_peer(brain_id)


def http_deliver(peer: Dict[str, Any], envelope: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
    """POST the envelope to the peer's pinned endpoint (SSRF-guarded like introduce)."""
    import httpx
    from api.hbar_commands import _validate_peer_url
    endpoint = (peer.get("endpoint") or "").rstrip("/")
    if not endpoint:
        return 0, {"detail": "peer has no endpoint"}
    _validate_peer_url(endpoint)
    r = httpx.post(endpoint + RECORD_PATH, json=envelope, timeout=15.0, follow_redirects=False)
    try:
        data = r.json()
    except Exception:
        data = {"detail": f"HTTP {r.status_code}"}
    return r.status_code, data if isinstance(data, dict) else {}


_DOORS: Dict[Tuple[str, str], Door] = {}
_DOORS_LOCK = threading.Lock()


def door_from_env() -> Door:
    """One Door per (brain, store path), so every request shares the store's lock."""
    brain_id, key = os.getenv("BRAIN_ID"), os.getenv("BRAIN_PRIVATE_KEY")
    if not brain_id or not key:
        raise RecordError(500, "BRAIN_ID or BRAIN_PRIVATE_KEY not configured")
    store = default_store()
    with _DOORS_LOCK:
        d = _DOORS.get((brain_id, str(store.path)))
        if d is None or d._key != key:
            d = Door(brain_id=brain_id, private_key=key, store=store,
                     pins=pinned_peer, deliver=http_deliver)
            _DOORS[(brain_id, str(store.path))] = d
        return d
