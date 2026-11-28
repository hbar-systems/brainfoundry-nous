"""The setup period, the console side (STEWARD-1, 2026-11-27). api/setup_steward.py holds the key.

Two things here:
1. While a setup period is open, the member's reasoner is told that the setup is in hand, so a setup
   question ("bring my folder", "why is X missing") gets the steward's page and the move-in card, not an
   invented import command with a token (seen 2026-11-27 on a member brain). It still searches Knowledge
   first (KNOWLEDGE-REACH-1, cc-job recall) when that door exists; this line does not repeat that one.
2. The steward's test turns: POST /setup/ask with the setup key runs one question through the member's
   own chat door (their seat, their persona, their memory), in its own thread labelled "Setup check" so
   the member sees it, and returns a verdict only: answered or not, how many of their documents it drew
   on, which of the expected words it used, whether it gave setup advice. The answer text stays on the
   brain. GET /setup/state gives the console's half of the state (seat, language, start page, layout).
"""
from __future__ import annotations

import json
import re
import threading
import time
import urllib.request
from typing import Any, Callable, Dict, List, Optional

KEY_HEADER = "X-Setup-Key"

# A setup answer the reasoner must not give while the steward runs: commands, tokens, paths.
_ADVICE = re.compile(
    r"(curl\s|bash\s|python3?\s|\bsudo\b|import-laptop|/home/|~/in\b|\.sh\b|\btoken\b|Bearer\s|X-Api-Key)",
    re.IGNORECASE)

NOTE = {
    "en": ("A setup period is open on this brain until {until}: a setup helper is finishing the person's "
           "move-in (copies, reading what they chose, checks). For any setup question (bringing files or "
           "chats in, why something is missing, import lines, passwords), do not write commands, tokens, "
           "file paths or import lines, and do not list setup steps. Search their Knowledge first; then say "
           "plainly what is already in, and that the rest is being handled; if a step is theirs, this page "
           "shows it: {page}."),
    "de": ("Auf diesem Gehirn läuft bis {until} eine Einrichtungszeit: ein Einrichtungshelfer macht den "
           "Umzug der Person fertig. Bei jeder Einrichtungsfrage (Dateien oder Chats hereinholen, warum etwas "
           "fehlt, Importzeilen, Passwörter) keine Befehle, Tokens, Dateipfade oder Importzeilen schreiben und "
           "keine Einrichtungsschritte aufzählen. Zuerst in ihrem Wissen suchen; dann schlicht sagen, was schon "
           "da ist und dass der Rest erledigt wird; wenn ein Schritt ihrer ist, zeigt ihn diese Seite: {page}. "
           "Antworte in der Sprache der Person."),
    "ru": ("На этом мозге до {until} идёт период настройки: помощник заканчивает переезд человека. На любой "
           "вопрос о настройке (перенести файлы или чаты, почему чего-то нет, строки импорта, пароли) не "
           "пиши команд, токенов, путей и строк импорта и не перечисляй шаги настройки. Сначала поищи в его "
           "Знаниях; потом просто скажи, что уже внутри и что остальное делается; если какой-то шаг его, он "
           "есть на этой странице: {page}. Отвечай на языке человека."),
}


def note(status: Optional[Dict[str, Any]], lang: str = "en", page: str = "/setup") -> str:
    """The standing line for this turn, or '' when no setup period is open."""
    if not status or not status.get("active"):
        return ""
    exp = status.get("expires_at")
    until = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(exp)) if exp else "the end of setup"
    return NOTE.get(lang, NOTE["en"]).format(until=until, page=page)


class Watch:
    """The api's /setup/status, asked at most once a minute (a turn never waits on it for long)."""

    def __init__(self, fetch: Callable[[], Optional[Dict[str, Any]]], ttl: float = 60.0, clock=time.monotonic):
        self.fetch, self.ttl, self.clock = fetch, ttl, clock
        self._at, self._val = -1e9, None
        self._lock = threading.Lock()

    def status(self) -> Optional[Dict[str, Any]]:
        with self._lock:
            if self.clock() - self._at < self.ttl:
                return self._val
        try:
            val = self.fetch()
        except Exception:  # noqa: BLE001 - no api, no note
            val = None
        with self._lock:
            self._at, self._val = self.clock(), val
        return val


def api_caller(base: str, key: str, timeout: float = 4.0):
    """(method, path, body) -> dict, with the brain's own key (the bridge's)."""

    def call(method: str, path: str, body: Optional[dict] = None) -> Optional[Dict[str, Any]]:
        if not key:
            return None
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(base.rstrip("/") + path, data=data, method=method,
                                     headers={"Content-Type": "application/json", "X-API-Key": key})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8") or "{}")

    return call


def key_ok(call, presented: str, scope: str) -> bool:
    if not presented or not presented.startswith("stw_") or len(presented) > 200:
        return False
    try:
        res = call("POST", "/setup/key/check", {"key": presented, "scope": scope}) or {}
    except Exception:  # noqa: BLE001 - fail closed
        return False
    return res.get("ok") is True


def verdict(reply: str, sources: List[str], expect: List[str], error: bool) -> Dict[str, Any]:
    """What the steward learns of one answer: no text."""
    low = (reply or "").lower()
    hits = [w for w in expect if w and w.lower() in low]
    named = [s for s in sources if s and _title(s).lower() in low]
    return {"answered": bool((reply or "").strip()) and not error, "chars": len(reply or ""),
            "drew_on": len(sources), "named_own": len(named), "expect_hits": hits,
            "expect_total": len([w for w in expect if w]),
            "setup_advice": bool(_ADVICE.search(reply or "")),
            "said_nothing_in": bool(_NOTHING.search(low))}


# "Nothing of yours is here": the failure seen 2026-11-27 over 2,027 documents, and its German and Russian forms.
_NOTHING = re.compile(
    r"(nothing (has been |was )?(uploaded|imported)|\bno (documents|files|notes|material)s?\b|(don't|do not) have any"
    r"|i (can't|cannot) (see|find) any|noch kein|nichts hochgeladen|keine [\w-]*(unterlagen|dateien|dokumente|notizen)"
    r"|ich sehe [\w\s-]{0,40}keine|ничего не загружено|не вижу|нет (файлов|документов))")


def _title(source: str) -> str:
    base = source.rsplit("/", 1)[-1]
    return base.rsplit(".", 1)[0] if "." in base[1:] else base


def ask(body: Dict[str, Any], turn: Callable[..., tuple], sources: Callable[[], List[str]],
        log: Callable[[str], Any]) -> tuple[int, Dict[str, Any]]:
    """One steward question through the member's chat door. turn = the bridge's _turn."""
    q = str((body or {}).get("question") or "").strip()
    if not q or len(q) > 2000:
        return 400, {"error": "one question, up to 2000 characters"}
    expect = [str(w)[:80] for w in ((body or {}).get("expect") or [])][:20]
    t0 = time.time()
    status, payload = turn(q, thread=None, new=True, source="steward", label="Setup check")
    reply = str((payload or {}).get("reply") or "")
    v = verdict(reply, list(sources() or []), expect, status != 200 or bool((payload or {}).get("error")))
    v["seconds"] = round(time.time() - t0, 1)
    v["thread"] = (payload or {}).get("thread")
    try:
        log(f"test question asked ({'answered' if v['answered'] else 'not answered'}, "
            f"{len(v['expect_hits'])} of {v['expect_total']} expected)")
    except Exception:  # noqa: BLE001
        pass
    return 200, v


def console_state(layout: Optional[Dict[str, Any]], health: Dict[str, Any], persona_chars: int,
                  turns: List[Dict[str, Any]]) -> Dict[str, Any]:
    """The console's half of the steward's state: what member-ready.sh items 4, 5, 7, 11 read."""
    c = (layout or {}).get("current") or {}
    p = c.get("panels") or {}
    codex = (health.get("codex") or {}).get("signedIn")
    claude = (health.get("auth") or {}).get("loggedIn")
    ok = sum(1 for t in turns if not t.get("error"))
    last = turns[-5:]
    return {"seat": "codex" if codex else ("claude" if claude else "none"),
            "lang": (layout or {}).get("lang") or "en", "start": c.get("start") or "",
            "quiet": p.get("hero") is False and p.get("nav") is False and p.get("tools") is False,
            "persona_chars": persona_chars, "turns": len(turns), "turns_ok": ok,
            "last_failed": bool(last) and all(t.get("error") for t in last)}
