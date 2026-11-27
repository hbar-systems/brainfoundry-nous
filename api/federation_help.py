"""
api/federation_help.py: "ask hbar", help between brains over the record door (MEMBERS-14, 2026-11-23).

hbar 2026-11-23: "if people have problems with their brains they can ask for help through
the Federation protocol".

A member presses "Something is wrong" in their console. Their brain signs a record of kind
"help.request" and hands it to its helper brain (a pinned peer named in data/help.json or
BRAIN_HELP_PEER) through the record door (api/federation_record.py). The helper's owner sees
it in Federation, Help, types an answer and presses Send; the helper's brain signs a
"help.answer" that goes back through the same door. Every check of the door holds: pinned
peers only, the signature against the pin, the size cap, the replay guard, the rate limit.

What a help record may carry, and nothing else (a record with any other field is refused,
by the sender before it signs and by the receiver at the door; a signed record cannot be
stripped without breaking its signature, so refusing is the only honest choice):

  help.request  body {screen, pressed[], words, lang, console_version}
                screen: a route, no query string; pressed: up to 8 press names from the
                console's closed alphabet (ui/lib/presses.js); words: the member's own words.
  help.answer   body {request_rid, words}; rid "<request rid>.answer"; ref = the request's
                hash. Accepted only for a help.request this brain really sent to that peer.

No memory content, no chat text, no file names, no persona: the shape has no room for them.
"""
from __future__ import annotations

import json
import os
import re
import secrets
from pathlib import Path
from typing import Any, Dict, List, Optional

from api.federation_record import ID_RE, Door, RecordError, record_hash

HELP_REQUEST = "help.request"
HELP_ANSWER = "help.answer"
HELP_KINDS = (HELP_REQUEST, HELP_ANSWER)
REQUEST_FIELDS = ("screen", "pressed", "words", "lang", "console_version")
ANSWER_FIELDS = ("request_rid", "words")
MAX_WORDS = 2000
MAX_PRESSED = 8
SCREEN_RE = re.compile(r"^/[a-z0-9/#:._-]{0,119}$")
PRESS_RE = re.compile(r"^[a-z0-9/#][a-z0-9/#:._-]{0,79}$")  # the alphabet of ui/lib/presses.js NAME_RE
LANG_RE = re.compile(r"^[a-z]{2,3}(-[a-z0-9]{2,8})?$")
VERSION_RE = re.compile(r"^[A-Za-z0-9._+-]{1,40}$")
REQ_RID_RE = re.compile(r"^help-[0-9]{10}-[0-9a-f]{12}$")
MAX_ASKS_PER_DAY = 10

NO_HELPER = "No helper is set on this brain yet, so this cannot be sent. Tell hbar in person."
NOT_PINNED = "The helper's brain is named here but not introduced on this brain yet, so this cannot be sent."


def _words(v: Any) -> str:
    if not isinstance(v, str) or not v.strip():
        raise RecordError(400, "help: words must be some text")
    if len(v) > MAX_WORDS:
        raise RecordError(400, f"help: words above {MAX_WORDS} characters")
    return v


def check_body(kind: str, body: Dict[str, Any], ref: Optional[str]) -> None:
    """The help shapes, exactly. Called by check_shape for every help.* record, both ways."""
    if kind == HELP_REQUEST:
        if set(body) != set(REQUEST_FIELDS):
            raise RecordError(400, "help.request carries only screen, pressed, words, lang, console_version")
        if not isinstance(body["screen"], str) or not SCREEN_RE.match(body["screen"]):
            raise RecordError(400, "help: screen must be a route without a query")
        p = body["pressed"]
        if not isinstance(p, list) or len(p) > MAX_PRESSED or not all(isinstance(x, str) and PRESS_RE.match(x) for x in p):
            raise RecordError(400, f"help: pressed is up to {MAX_PRESSED} press names")
        _words(body["words"])
        if not isinstance(body["lang"], str) or not LANG_RE.match(body["lang"]):
            raise RecordError(400, "help: bad lang")
        if not isinstance(body["console_version"], str) or not VERSION_RE.match(body["console_version"]):
            raise RecordError(400, "help: bad console_version")
        if ref is not None:
            raise RecordError(400, "help.request answers nothing")
    elif kind == HELP_ANSWER:
        if set(body) != set(ANSWER_FIELDS):
            raise RecordError(400, "help.answer carries only request_rid and words")
        if not isinstance(body["request_rid"], str) or not REQ_RID_RE.match(body["request_rid"]):
            raise RecordError(400, "help: bad request_rid")
        _words(body["words"])
        if ref is None:
            raise RecordError(400, "help.answer needs ref")
    else:
        raise RecordError(400, "unknown help kind")


def check_inbound(door: Door, rec: Dict[str, Any]) -> None:
    """Store checks at the receiving door: an answer must answer a request this brain sent."""
    if rec["kind"] == HELP_REQUEST:
        if not REQ_RID_RE.match(rec["rid"]):
            raise RecordError(400, "help: bad rid")
        return
    req_rid = rec["body"]["request_rid"]
    if rec["rid"] != f"{req_rid}.answer":
        raise RecordError(400, "help: answer rid must be <request rid>.answer")
    orig = door.store.state().get(f"{door.id}/{req_rid}")
    if not orig or orig.get("dir") != "out" or orig["record"]["kind"] != HELP_REQUEST or orig["record"]["to"] != rec["from"]:
        raise RecordError(404, "answers no help request this brain sent to you")
    if record_hash(orig["record"]) != rec["ref"]:
        raise RecordError(409, "ref does not match the help request sent")


# ---------------------------------------------------------------- config

def config() -> Dict[str, Any]:
    """{"helper": "<brain id>" or None, "button": bool}. BRAIN_HELP_PEER wins over data/help.json.

    The button (CHIP-1, 2026-11-27): it is a member's line to their helper, so a brain with no
    helper of its own (the helper's owner, hbar, is the one asked) shows it off by default; a
    member's brain shows it on. data/help.json {"button": true|false} overrides either way."""
    cfg: Dict[str, Any] = {}
    p = Path(os.getenv("HELP_CONFIG_PATH", "data/help.json"))
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            cfg = raw
    except Exception:
        pass
    helper = (os.getenv("BRAIN_HELP_PEER") or cfg.get("helper") or "").strip()
    helper = helper if helper and ID_RE.match(helper) else None
    button = cfg.get("button")
    return {"helper": helper, "button": bool(helper) if not isinstance(button, bool) else button}


# ---------------------------------------------------------------- the member's side

def _answers(door: Door) -> Dict[str, Dict[str, Any]]:
    out = {}
    for s in door.store.state().values():
        r = s["record"]
        if s.get("dir") == "in" and r["kind"] == HELP_ANSWER:
            out[r["body"]["request_rid"]] = {"words": r["body"]["words"], "at": s["receipt"]["at"], "from": r["from"]}
    return out


def status(door: Door) -> Dict[str, Any]:
    cfg = config()
    helper = cfg["helper"]
    ready = bool(helper and door.pins(helper))
    message = None if ready else (NOT_PINNED if helper else NO_HELPER)
    answers = _answers(door)
    asked = []
    for s in door.store.state().values():
        r = s["record"]
        if s.get("dir") == "out" and r["kind"] == HELP_REQUEST:
            asked.append({"rid": r["rid"], "to": r["to"], "iat": r["iat"], "screen": r["body"]["screen"],
                          "words": r["body"]["words"], "delivered": "receipt" in s,
                          "last_error": None if "receipt" in s else s.get("last_error"),
                          "answer": answers.get(r["rid"])})
    asked.sort(key=lambda a: a["iat"], reverse=True)
    return {"helper": helper, "ready": ready, "message": message, "button": cfg["button"], "asked": asked}


def ask(door: Door, *, screen: str, pressed: List[str], words: str, lang: str, console_version: str) -> Dict[str, Any]:
    cfg = config()
    helper = cfg["helper"]
    if not helper:
        raise RecordError(409, NO_HELPER)
    if not door.pins(helper):
        raise RecordError(409, NOT_PINNED)
    now = door._now()
    recent = [s for s in door.store.state().values() if s.get("dir") == "out"
              and s["record"]["kind"] == HELP_REQUEST and s["record"]["iat"] > now - 86400]
    if len(recent) >= MAX_ASKS_PER_DAY:
        raise RecordError(429, f"{MAX_ASKS_PER_DAY} asks today already; hbar has them")
    screen = (screen or "/").split("?")[0].split("#")[0].lower()[:120] or "/"
    if not SCREEN_RE.match(screen):
        screen = "/"
    body = {"screen": screen,
            "pressed": [p for p in (pressed or []) if isinstance(p, str) and PRESS_RE.match(p)][-MAX_PRESSED:],
            "words": words, "lang": (lang or "en").lower(), "console_version": console_version}
    rid = f"help-{now:010d}-{secrets.token_hex(6)}"
    row = door.send(kind=HELP_REQUEST, to=helper, rid=rid, body=body)
    return dict(row, rid=rid)


# ---------------------------------------------------------------- the helper's side

def inbox(door: Door) -> Dict[str, Any]:
    st = door.store.state()
    out = []
    for s in st.values():
        r = s["record"]
        if s.get("dir") != "in" or r["kind"] != HELP_REQUEST:
            continue
        ans = st.get(f"{door.id}/{r['rid']}.answer")
        out.append({"from": r["from"], "rid": r["rid"], "iat": r["iat"], "at": s["receipt"]["at"], **r["body"],
                    "answered": bool(ans), "answer_words": ans["record"]["body"]["words"] if ans else None,
                    "answer_delivered": bool(ans and "receipt" in ans),
                    "answer_error": ans.get("last_error") if ans and "receipt" not in ans else None})
    out.sort(key=lambda x: x["iat"], reverse=True)
    return {"requests": out, "open": sum(1 for x in out if not x["answered"])}


def answer(door: Door, *, frm: str, rid: str, words: str) -> Dict[str, Any]:
    s = door.store.state().get(f"{frm}/{rid}")
    if not s or s.get("dir") != "in" or s["record"]["kind"] != HELP_REQUEST:
        raise RecordError(404, "no such help request")
    arid = f"{rid}.answer"
    if f"{door.id}/{arid}" in door.store.state():
        return door.redeliver(arid)  # answered already: the same answer, delivered if it was not
    return door.send(kind=HELP_ANSWER, to=frm, rid=arid, ref=record_hash(s["record"]),
                     body={"request_rid": rid, "words": _words(words)})
