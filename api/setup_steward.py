"""The setup period (STEWARD-1, 2026-11-27): a helper finishes a member's move-in without the operator
relaying screens, under a key the member consented to, scoped to setup actions, with an end.

Why: a member's move-in took four days of the operator at her laptop reading photos into a thread (import
stalls, three counts, a lost queue, a re-run that brought 95 files twice, her own brain inventing an import
line because it could not see what it held). The steward run (operator tooling, outside this template)
does the setup through these doors instead, and stops at the steps only a person can do.

The key
- Minted by the member's own press on their console (owner key, through the console proxy): POST /setup/key
  with the consent line they were shown (its sha) and a life of at most 72 h (default 48 h).
- The raw key is never shown on any screen and never returned by the api. It is written once to
  <runtime>/setup/steward.key (mode 600), where the operator's steward run collects it on the box
  (the same trust as the ready check, which already reads the brain's .env counts as root).
- Stored as a sha256; checked in constant time; dead at its end, at POST /setup/revoke, or at handover.
- Scopes, and only these: state (counts, never titles or text), duplicates (reject pending copies of what
  is already held), approve (start reading what the person chose), ask (a test question through the
  console's chat door, the bridge checks the key here), log. Nothing else answers to it: no stored
  document is deleted, no persona, setting, key, export, Update or password is reachable.

What the steward sees: counts and pass/fail. The duplicate test and the chosen set are worked out here,
on the brain; the steward gets numbers back. Every action is one line in <runtime>/setup/log.jsonl and the
api's log; GET /setup/status shows the last one to the member.

Handover: the member picks a new console password on a guided screen (POST /setup/handover/password: the
api hashes it, bcrypt, keeps only the hash, mode 600); the operator's press on the box
(scripts/setup-handover.sh) swaps it into the console's Caddy block and ends the key. Pure parts
(duplicates, chosen, consent, Caddy line swap) are functions here so they are tested without a brain.
"""

import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Protocol

SCOPES = ("state", "duplicates", "approve", "ask", "log")
DEFAULT_TTL_HOURS = 48
MAX_TTL_HOURS = 72
KEY_HEADER = "X-Setup-Key"

# The line the member sees before the one press that lets the helper in. Counts, never contents: the
# helper's answers come back as pass or fail. {until} is the end date in the member's words.
CONSENT = {
    "en": ("Let the setup helper finish moving you in, until {until}. It sees counts, never your files "
           "or chats. It clears copies that came twice, reads in what you chose, and asks your brain a few "
           "test questions. It cannot change your words, see your passwords or delete what you kept. It "
           "stops on {until}, or when you press Done."),
    "de": ("Der Einrichtungshelfer darf deinen Umzug bis {until} fertig machen. Er sieht nur Zahlen, nie "
           "deine Dateien oder Chats. Er entfernt doppelt Angekommenes, liest ein, was du gewählt hast, und "
           "stellt deinem Gehirn ein paar Testfragen. Er kann deine Worte nicht ändern, deine Passwörter "
           "nicht sehen und nichts löschen, was du behalten hast. Er hört am {until} auf, oder wenn du "
           "Fertig drückst."),
    "ru": ("Помощник настройки может закончить твой переезд до {until}. Он видит только числа, никогда "
           "твои файлы или чаты. Он убирает то, что пришло дважды, читает то, что ты выбрал(а), и задаёт "
           "твоему мозгу несколько проверочных вопросов. Он не может менять твои слова, видеть твои "
           "пароли или удалять то, что ты оставил(а). Он остановится {until} или когда ты нажмёшь Готово."),
}


def consent_text(lang: str, until: str) -> str:
    return CONSENT.get(lang, CONSENT["en"]).format(until=until)


def consent_sha(lang: str) -> str:
    """The sha of the line's template (the date varies, the promise does not)."""
    return hashlib.sha256(CONSENT.get(lang, CONSENT["en"]).encode("utf-8")).hexdigest()


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


class SetupError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status, self.detail = status, detail


class SetupKeys:
    """One setup key at a time per brain: minted on the member's yes, checked by scope, ended by time,
    revoke or handover. State in <dir>/key.json (hash only), the raw key once in <dir>/steward.key."""

    def __init__(self, base: Path, clock: Callable[[], float] = time.time):
        self.dir = Path(base)
        self.clock = clock
        self._lock = threading.Lock()

    # -- files
    def _rec(self) -> Optional[Dict[str, Any]]:
        try:
            return json.loads((self.dir / "key.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def _write(self, name: str, text: str) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.dir, 0o700)
        except OSError:
            pass
        p = self.dir / name
        tmp = p.with_suffix(p.suffix + ".tmp")
        fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, p)

    def log(self, action: str, by: str = "steward", **detail: Any) -> Dict[str, Any]:
        row = {"at": int(self.clock()), "by": by, "action": action, **detail}
        self.dir.mkdir(parents=True, exist_ok=True)
        with open(self.dir / "log.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(f"[setup] {by}: {action} {json.dumps(detail, ensure_ascii=False)[:300]}", flush=True)
        return row

    def tail(self, n: int = 50) -> List[Dict[str, Any]]:
        try:
            lines = (self.dir / "log.jsonl").read_text(encoding="utf-8").splitlines()[-n:]
        except OSError:
            return []
        out = []
        for line in lines:
            try:
                out.append(json.loads(line))
            except ValueError:
                pass
        return out

    # -- the key
    def mint(self, *, lang: str, text_sha: str, ttl_hours: Optional[float] = None, by: str = "member") -> Dict[str, Any]:
        if not hmac.compare_digest(str(text_sha or ""), consent_sha(lang)):
            raise SetupError(400, "the consent line shown is not the current one; show it again")
        ttl = float(ttl_hours or DEFAULT_TTL_HOURS)
        if not 0 < ttl <= MAX_TTL_HOURS:
            raise SetupError(400, f"a setup key lives at most {MAX_TTL_HOURS} h")
        raw = "stw_" + secrets.token_urlsafe(32)
        now = self.clock()
        rec = {"sha": _sha(raw), "scopes": list(SCOPES), "minted_at": int(now), "expires_at": int(now + ttl * 3600),
               "by": by, "lang": lang, "consent_sha": consent_sha(lang), "revoked_at": None}
        with self._lock:
            self._write("steward.key", raw + "\n")
            self._write("key.json", json.dumps(rec))
        self.log("key minted", by=by, expires_at=rec["expires_at"], scopes=rec["scopes"])
        return {k: rec[k] for k in ("scopes", "minted_at", "expires_at", "by")}

    def check(self, raw: Optional[str], scope: str) -> Dict[str, Any]:
        if scope not in SCOPES:
            raise SetupError(403, "not a setup action")
        rec = self._rec()
        if not raw or not rec or not hmac.compare_digest(_sha(raw), rec.get("sha") or ""):
            raise SetupError(401, "no setup key, or not this brain's")
        if rec.get("revoked_at"):
            raise SetupError(401, "the setup period has ended")
        if self.clock() >= rec.get("expires_at", 0):
            raise SetupError(401, "the setup key has run out")
        if scope not in rec.get("scopes", []):
            raise SetupError(403, f"the setup key does not cover {scope}")
        return rec

    def active(self) -> bool:
        rec = self._rec()
        return bool(rec and not rec.get("revoked_at") and self.clock() < rec.get("expires_at", 0))

    def revoke(self, by: str = "member", why: str = "revoked") -> Dict[str, Any]:
        with self._lock:
            rec = self._rec()
            if rec and not rec.get("revoked_at"):
                rec["revoked_at"] = int(self.clock())
                self._write("key.json", json.dumps(rec))
            try:
                (self.dir / "steward.key").unlink()
            except OSError:
                pass
        last = self.last_steward_action()
        self.log("setup ended", by=by, why=why)
        return {"active": False, "last_steward_action": last}

    def last_steward_action(self) -> Optional[Dict[str, Any]]:
        for row in reversed(self.tail(200)):
            if row.get("by") == "steward":
                return row
        return None

    def status(self) -> Dict[str, Any]:
        rec = self._rec() or {}
        return {"active": self.active(), "expires_at": rec.get("expires_at"), "minted_at": rec.get("minted_at"),
                "revoked_at": rec.get("revoked_at"), "scopes": rec.get("scopes") or [],
                "last_action": (self.tail(1) or [None])[0], "last_steward_action": self.last_steward_action(),
                "password_chosen": (self.dir / "console-hash").exists()}

    # -- handover: the member's own new console password, kept as a hash only
    def keep_password_hash(self, password: str, hasher: Callable[[str], str]) -> Dict[str, Any]:
        if not isinstance(password, str) or len(password) < 10 or len(password) > 200:
            raise SetupError(400, "a password of 10 to 200 characters")
        if len(set(password)) < 5:
            raise SetupError(400, "a password with more different characters")
        h = hasher(password)
        if not re.fullmatch(r"\$2[aby]\$\d\d\$[./A-Za-z0-9]{53}", h or ""):
            raise SetupError(500, "the hash did not come out as bcrypt")
        with self._lock:
            self._write("console-hash", h + "\n")
        self.log("new console password chosen", by="member")
        return {"password_chosen": True}


def bcrypt_hasher(password: str) -> str:
    """bcrypt, the hash Caddy's basicauth reads (cost 12)."""
    try:
        import bcrypt  # api/requirements.txt (STEWARD-1)
    except ImportError as e:  # pragma: no cover - the image has it
        raise SetupError(501, "this brain's api has no bcrypt yet (update it)") from e
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(12)).decode("ascii")


# ---------------------------------------------------------------- pure parts


def _name(p: Dict[str, Any]) -> str:
    return (p.get("source_refs") or {}).get("filename") or ""


def _norm(t: str) -> str:
    return re.sub(r"\s+", " ", (t or "")).strip()


def duplicates(pending: List[Dict[str, Any]], stored: List[Dict[str, Any]],
               text_of: Callable[[str], Optional[str]]) -> Dict[str, Any]:
    """Which pending proposals are copies, worked out on the brain.

    1. A pending file whose name is already held and whose text starts as the held one does (the held
       document's first 400 characters, the Knowledge synopsis): a copy of a stored document (the re-run
       import that brought 95 files twice). Same name, different start: a newer version, left for the person.
    2. Two pending with the same text (same file under two names, or the same name twice): the first by
       name (shortest path, then alphabetical) stays, the rest are copies.
    Returns {"copies": [{"proposal_id", "of"}], "changed": n}; a proposal whose text is gone is never a copy.
    """
    held = {d.get("name"): _norm(d.get("synopsis") or "")[:300] for d in stored if d.get("name")}
    copies: List[Dict[str, str]] = []
    changed = 0
    seen_text: Dict[str, str] = {}
    rows = []
    for p in pending:
        pid = p.get("proposal_id")
        text = text_of(pid) if pid else None
        if not pid or text is None:
            continue
        rows.append((p, _norm(text)))
    rows.sort(key=lambda r: (len(_name(r[0])), _name(r[0])))
    for p, text in rows:
        name, pid = _name(p), p["proposal_id"]
        if name in held:
            if held[name] and text[:300] == held[name]:
                copies.append({"proposal_id": pid, "of": "stored"})
                continue
            changed += 1
        key = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if key in seen_text:
            copies.append({"proposal_id": pid, "of": "pending"})
            continue
        seen_text[key] = pid
    return {"copies": copies, "changed": changed}


def chosen(pending: List[Dict[str, Any]], intent: Optional[Dict[str, Any]], survey: Optional[Dict[str, Any]],
           chat_doc: Callable[[str], bool]) -> List[Dict[str, Any]]:
    """What the person already said yes to, among the pending: the ids of their "Remember all" (and its
    kind: documents, chats, all), and the files of a computer run whose map they chose. Nothing else."""
    want_ids = set((intent or {}).get("ids") or [])
    kind = (intent or {}).get("kind")
    survey_chosen = bool(survey and survey.get("chosen") is not None)
    since = (survey or {}).get("run_created")
    out = []
    for p in pending:
        n = _name(p)
        if p.get("proposal_id") in want_ids:
            out.append(p)
        elif kind == "all" or (kind == "chats" and chat_doc(n)) or (kind == "documents" and not chat_doc(n)):
            out.append(p)
        elif survey_chosen and n.startswith("laptop/"):
            out.append(p)
        elif survey_chosen and since and chat_doc(n) and _epoch(p.get("created_at")) >= float(since):
            # the run's Codex and Claude Code sessions land under chat names, not laptop/ (MEMBERS-11)
            out.append(p)
    return out


def _epoch(v: Any) -> float:
    """A proposal's created_at (epoch seconds or ISO 8601) as epoch seconds; 0 when unreadable."""
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str) and v:
        from datetime import datetime, timezone
        try:
            d = datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError:
            return 0.0
        return (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).timestamp()
    return 0.0


def swap_console_hash(caddyfile: str, host_prefix: str, user: str, new_hash: str) -> str:
    """The console site block whose address starts with host_prefix (for example "console.anne."): the
    basicauth line for user gets new_hash. Exactly one line must change, else ValueError (nothing written)."""
    if not re.fullmatch(r"\$2[aby]\$\d\d\$[./A-Za-z0-9]{53}", new_hash):
        raise ValueError("not a bcrypt hash")
    lines = caddyfile.split("\n")
    depth, inside, changed = 0, False, 0
    for i, line in enumerate(lines):
        s = line.strip()
        if depth == 0 and s.endswith("{") and any(a.strip().startswith(host_prefix) for a in s[:-1].split(",")):
            inside = True
        if inside and depth >= 1:
            m = re.match(r"^(\s*)(\S+)(\s+)(\$2[aby]\$\S+)\s*$", line)
            if m and m.group(2) == user:
                lines[i] = f"{m.group(1)}{user}{m.group(3)}{new_hash}"
                changed += 1
        depth += line.count("{") - line.count("}")
        if inside and depth == 0:
            inside = False
    if changed != 1:
        raise ValueError(f"expected one password line for {user} under {host_prefix}, found {changed}")
    return "\n".join(lines)


# ---------------------------------------------------------------- the doors


class Backend(Protocol):
    def pending(self) -> List[Dict[str, Any]]: ...
    def stored(self) -> List[Dict[str, Any]]: ...
    def text_of(self, proposal_id: str) -> Optional[str]: ...
    def reject(self, proposal_id: str, note: str) -> None: ...
    def approve(self, items: List[Dict[str, Any]]) -> Dict[str, Any]: ...
    def waiting(self) -> Dict[str, Any]: ...
    def intent(self) -> Optional[Dict[str, Any]]: ...
    def survey(self) -> Optional[Dict[str, Any]]: ...
    def held_high(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]: ...
    def chat_doc(self, name: str) -> bool: ...
    def facts(self) -> Dict[str, Any]: ...


def knowledge_counts(stored: Iterable[Dict[str, Any]], chat_doc: Callable[[str], bool]) -> Dict[str, int]:
    docs = list(stored)
    chats = sum(1 for d in docs if chat_doc(d.get("name") or ""))
    laptop = sum(1 for d in docs if (d.get("name") or "").startswith("laptop/"))
    return {"documents": len(docs), "chats": chats, "laptop": laptop, "other": len(docs) - chats - laptop}


def make_router(keys: SetupKeys, backend: Backend, get_api_key: Callable, hasher: Callable[[str], str] = bcrypt_hasher):
    from fastapi import APIRouter, Depends, Header, HTTPException, Request

    router = APIRouter()

    def guard(scope: str):
        def dep(x_setup_key: Optional[str] = Header(None, alias=KEY_HEADER)) -> Dict[str, Any]:
            try:
                return keys.check(x_setup_key, scope)
            except SetupError as e:
                raise HTTPException(status_code=e.status, detail=e.detail)
        return dep

    def wrap(fn):
        try:
            return fn()
        except SetupError as e:
            raise HTTPException(status_code=e.status, detail=e.detail)

    # -- the member's side (owner key: their console)
    @router.get("/setup/consent")
    def setup_consent(lang: str = "en", api_key: str = Depends(get_api_key)):
        until = time.strftime("%Y-%m-%d", time.gmtime(time.time() + DEFAULT_TTL_HOURS * 3600))
        return {"text": consent_text(lang, until), "sha": consent_sha(lang), "until": until,
                "ttl_hours": DEFAULT_TTL_HOURS, "lang": lang if lang in CONSENT else "en"}

    @router.post("/setup/key")
    async def setup_key(request: Request, api_key: str = Depends(get_api_key)):
        body = await _body(request)
        if body.get("consent") is not True:
            raise HTTPException(400, "the member's yes is missing")
        return wrap(lambda: keys.mint(lang=str(body.get("lang") or "en"), text_sha=str(body.get("text_sha") or ""),
                                      ttl_hours=body.get("ttl_hours"), by=str(body.get("by") or "member")[:40]))

    @router.post("/setup/revoke")
    async def setup_revoke(request: Request, api_key: str = Depends(get_api_key)):
        body = await _body(request)
        return keys.revoke(by=str(body.get("by") or "member")[:40], why=str(body.get("why") or "revoked")[:120])

    @router.post("/setup/handover/password")
    async def setup_password(request: Request, api_key: str = Depends(get_api_key)):
        body = await _body(request)
        if body.get("password") != body.get("again"):
            raise HTTPException(400, "the two passwords differ")
        return wrap(lambda: keys.keep_password_hash(body.get("password") or "", hasher))

    @router.get("/setup/status")
    def setup_status(api_key: str = Depends(get_api_key)):
        return keys.status()

    @router.post("/setup/key/check")
    async def setup_key_check(request: Request, api_key: str = Depends(get_api_key)):
        """For the console bridge: is this setup key good for this scope (its /setup/ask and /setup/state)."""
        body = await _body(request)
        try:
            keys.check(str(body.get("key") or ""), str(body.get("scope") or ""))
        except SetupError as e:
            return {"ok": False, "why": e.detail}
        return {"ok": True}

    @router.post("/setup/log/append")
    async def setup_log_append(request: Request, api_key: str = Depends(get_api_key)):
        """The bridge records the steward's test turns here, so the member's log has them in one place."""
        body = await _body(request)
        return keys.log(str(body.get("action") or "")[:200], by="steward", via="console")

    # -- the steward's side (setup key)
    @router.get("/setup/state")
    def setup_state(rec: Dict[str, Any] = Depends(guard("state"))):
        stored, pending = backend.stored(), backend.pending()
        dup = duplicates(pending, stored, backend.text_of)
        ch = chosen(pending, backend.intent(), backend.survey(), backend.chat_doc)
        held = backend.held_high(ch)
        w = backend.waiting()
        sv = backend.survey() or {}
        return {"facts": backend.facts(), "knowledge": knowledge_counts(stored, backend.chat_doc),
                "waiting": {k: w.get(k) for k in ("documents", "chats", "total")},
                "reading": w.get("reading") or {}, "remember": w.get("remember"),
                "duplicates": {"copies": len(dup["copies"]), "changed": dup["changed"]},
                "chosen_waiting": len(ch) - len(held), "held_for_a_look": len(held),
                "survey": {"state": sv.get("state"), "refused_total": sv.get("refused_total") or 0,
                           "refused_by": sv.get("refused_by") or {}, "retry_open": bool(sv.get("retry"))},
                "setup": {"expires_at": rec.get("expires_at")}}

    @router.post("/setup/duplicates/clear")
    async def setup_dups(request: Request, rec: Dict[str, Any] = Depends(guard("duplicates"))):
        body = await _body(request)
        dup = duplicates(backend.pending(), backend.stored(), backend.text_of)
        n = 0
        if not body.get("dry_run"):
            for c in dup["copies"]:
                backend.reject(c["proposal_id"], f"setup: copy of a {c['of']} document")
                n += 1
            keys.log("cleared copies", copies=n, ids=[c["proposal_id"] for c in dup["copies"]][:2000])
        return {"copies": len(dup["copies"]), "cleared": n, "changed_left_for_the_person": dup["changed"]}

    @router.post("/setup/approve")
    def setup_approve(rec: Dict[str, Any] = Depends(guard("approve"))):
        ch = chosen(backend.pending(), backend.intent(), backend.survey(), backend.chat_doc)
        held = backend.held_high(ch)
        gone = {p["proposal_id"] for p in held}
        items = [p for p in ch if p["proposal_id"] not in gone]
        res = backend.approve(items) if items else {"started": False}
        keys.log("reading what the person chose", items=len(items), held=len(held))
        return {"queued": len(items), "held_for_a_look": len(held),
                "running": bool((res or {}).get("running") or (res or {}).get("started"))}

    @router.get("/setup/log")
    def setup_log(rec: Dict[str, Any] = Depends(guard("log"))):
        return {"log": keys.tail(50)}

    return router


async def _body(request) -> Dict[str, Any]:
    raw = await request.body()
    if len(raw) > 20000:
        from fastapi import HTTPException
        raise HTTPException(413, "too large")
    try:
        d = json.loads(raw or b"{}")
    except ValueError:
        d = {}
    return d if isinstance(d, dict) else {}
