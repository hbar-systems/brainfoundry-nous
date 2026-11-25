"""Bring in this computer: the dial-out agent (SPOKE-3 "Courier", hbar 2026-11-16, docs/IMPORT.md).

The member copies ONE line from the home card into Terminal (Mac, Linux) or PowerShell (Windows):

    curl -fsSL https://<brain>/api/bf/laptop/agent.sh | bash -s -- imp_...
    $env:BRAIN_TOKEN="imp_..."; irm https://<brain>/api/bf/laptop/agent.ps1 | iex

The script comes from the person's own brain (GET /laptop/agent.sh, /laptop/agent.ps1; this module
renders it) and needs nothing installed: bash, curl, find, stat, awk and gzip on a Mac, PowerShell 5.1
on Windows. No Python, no app bundle (so no Gatekeeper or SmartScreen "unknown developer" warning,
and no Apple Developer ID), no SSH server, no VPN, no router change. The laptop only calls OUT over
HTTPS to the token door MOVE-IN-2 set (/documents/import-laptop/check, file, finish); the brain never
opens a connection to the laptop. One run, then the agent closes the key, deletes its temp folder
and exits.

The never-send rules are not copied by hand into the two scripts: they are rendered here from
scripts/import/brain_import.py (SKIP_DIRS, SKIP_FILES, READABLE, AUDIO, caps), so the Python helper
and both agents keep one list. The script routes are public GETs (the script is no secret; the key
is in the line, never in the address), carry no state, and answer the same text to anyone, apart
from the brain address taken from the request's Host.
"""
import fnmatch
import importlib.util
import re
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IMPORT_DIR = ROOT / "scripts" / "import"
HELPER = IMPORT_DIR / "brain_import.py"
TEMPLATES = {"sh": IMPORT_DIR / "agent.sh", "ps1": IMPORT_DIR / "agent.ps1"}
DIR_SUFFIXES = (".photoslibrary", ".app", ".bundle", ".framework")
HOST_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?(?::[0-9]{1,5})?$")
LOOPBACK = ("127.0.0.1", "localhost")
PREFIX = "/api/bf"  # the console's address of the api; Caddy opens these paths straight to the api


@lru_cache(maxsize=1)
def helper():
    """scripts/import/brain_import.py as a module (its rule lists only; nothing runs)."""
    spec = importlib.util.spec_from_file_location("brain_import_rules", HELPER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def glob_ere(pat: str) -> str:
    """One fnmatch pattern as a POSIX ERE piece for awk: '*' any, '?' one, every other character
    literal (in a bracket, so no backslash escapes travel through awk)."""
    out = []
    for ch in pat:
        if ch == "*":
            out.append(".*")
        elif ch == "?":
            out.append(".")
        elif ch.isalnum() or ch in "_- ":
            out.append(ch)
        elif ch == "^":
            out.append("\\^")
        else:
            out.append(f"[{ch}]")
    return "".join(out)


def rules() -> dict:
    h = helper()
    return {
        "skip_dirs": sorted(h.SKIP_DIRS),
        "dir_suffixes": list(DIR_SUFFIXES),
        "skip_files": list(h.SKIP_FILES),
        "secret_re": "^(" + "|".join(glob_ere(p) for p in h.SKIP_FILES) + ")$",
        "readable": sorted(h.READABLE),
        "audio": sorted(h.AUDIO),
        "images": sorted(h.IMAGES),
        "max_file": h.MAX_FILE_BYTES,
        "max_audio": h.MAX_AUDIO_FILE_BYTES,
        "max_entries": h.MAX_ENTRIES,
        # the coding agents' history roots (MEMBERS-11): (label, "dir/dir" under the home, depth)
        "history": [(label, "/".join(parts), depth) for label, parts, depth in h.AGENT_HISTORY],
        "history_ext": h.HISTORY_EXT,
    }


def is_secret(name: str) -> bool:
    """The helper's own test, for the tests to hold the rendered regex against."""
    low = name.lower()
    return any(fnmatch.fnmatch(low, p) for p in helper().SKIP_FILES)


# ── the words the agent prints, en and ru ({0}, {1} are filled in order) ──
WORDS = {
    "en": {
        "BADTOKEN": "This needs the line from your brain's home, with its key (imp_...). Make a new line there: Bring in this computer.",
        "BADBASE": "The brain's address must start with https://",
        "MISSING": "This computer has no {0}; tell the person who set up your brain.",
        "REFUSED": "Your brain did not take this ({0}): {1}. Make a new line on your brain's home.",
        "NOTSURVEY": "This line is for another kind of import. Make a new line on your brain's home: Bring in this computer.",
        "CONNECTED": "Connected to your brain.",
        "LOOKING": "Looking through this computer: names, sizes and dates only. Nothing is read or sent yet.",
        "MACASK": "If your Mac asks whether Terminal may open Desktop, Documents, Downloads or iCloud Drive, press Allow (OK).",
        "ROOT": "  and in {0}",
        "FOUND": "Found {0} files your brain can take ({1}).",
        "CLOUDS": "Cloud folders: {0}.",
        "NOCLOUDS": "No cloud folders found.",
        "HISTORY": "Your Codex and Claude Code history on this computer comes along, each session as one conversation: {0}.",
        "NEVER": "Never sent, only counted: {0} files (keys, passwords, hidden files, mail, browser data, video, archives, files too big).",
        "PRIVATE": "The computer kept these private, so they were not looked at: {0}. To include them, run the line again and press Allow when asked.",
        "LISTSENT": "The list is on your brain: {0} files in {1} groups.",
        "CHOOSE": "Now open your brain's home in the browser and choose what to bring. Keep this window open; it waits for you (Ctrl+C stops it).",
        "EXPIRED": "The line expired or was closed before a choice. Nothing was sent.",
        "CHOSE": "You chose {0} files ({1}). Bringing them now.",
        "IGNORED": "{0} names the brain asked for were not on this computer's list and were not sent.",
        "OK": "ok",
        "KEPT": "kept as a file",
        "REFUSEDONE": "not taken ({0})",
        "STOPPED": "The line stopped working; the rest was not sent.",
        "ABORTED": "Stopped. The line is closed; nothing more is sent.",
        "DONE": "Done: {0} sent, {1} not taken. Nothing stays on this computer: the temporary folder is deleted and nothing keeps running. You can close this window.",
        "ASKTOKEN": "Paste the key from your brain's home (imp_...)",
        "LOOKONLY": "Looked only: nothing was sent and nothing was kept.",
        "WAITBRAIN": "  your brain is busy reading; trying again in {0} s",
        "REFUSEDBY": "Not taken, by reason: {0}.",
        "REASON_too_big": "too big", "REASON_type": "a type Knowledge does not read", "REASON_busy": "brain busy",
        "REASON_gone": "no longer on this computer", "REASON_other": "other",
        "RETRYASK": "{0} of them can be sent again. Press Return here, or Send these again on your brain's home (waits 10 minutes).",
        "RETRYING": "Sending the {0} again.",
    },
    "ru": {
        "BADTOKEN": "Нужна строка с главной страницы вашего мозга, с ключом (imp_...). Сделайте там новую строку: «Перенести этот компьютер».",
        "BADBASE": "Адрес мозга должен начинаться с https://",
        "MISSING": "На этом компьютере нет {0}; скажите тому, кто настраивал ваш мозг.",
        "REFUSED": "Мозг не принял это ({0}): {1}. Сделайте новую строку на главной странице мозга.",
        "NOTSURVEY": "Эта строка для другого переноса. Сделайте новую строку на главной странице мозга: «Перенести этот компьютер».",
        "CONNECTED": "Связь с вашим мозгом есть.",
        "LOOKING": "Просматриваю компьютер: только названия, размеры и даты. Пока ничего не читается и не отправляется.",
        "MACASK": "Если Mac спросит, можно ли Терминалу открыть Рабочий стол, Документы, Загрузки или iCloud Drive, нажмите «Разрешить» (OK).",
        "ROOT": "  и в {0}",
        "FOUND": "Нашлось {0} файлов, которые мозг может взять ({1}).",
        "CLOUDS": "Облачные папки: {0}.",
        "NOCLOUDS": "Облачных папок нет.",
        "HISTORY": "История Codex и Claude Code на этом компьютере тоже переносится, каждая сессия одним разговором: {0}.",
        "NEVER": "Не отправляются никогда, только считаются: {0} файлов (ключи, пароли, скрытые файлы, почта, данные браузера, видео, архивы, слишком большие).",
        "PRIVATE": "Компьютер закрыл эти папки, их не смотрели: {0}. Чтобы добавить их, запустите строку ещё раз и нажмите «Разрешить», когда спросят.",
        "LISTSENT": "Список у мозга: {0} файлов в {1} группах.",
        "CHOOSE": "Теперь откройте главную страницу мозга в браузере и выберите, что перенести. Не закрывайте это окно, оно ждёт (Ctrl+C остановит).",
        "EXPIRED": "Строка истекла или закрыта до выбора. Ничего не отправлено.",
        "CHOSE": "Вы выбрали {0} файлов ({1}). Переношу.",
        "IGNORED": "{0} названий, которые попросил мозг, не было в списке этого компьютера; они не отправлены.",
        "OK": "готово",
        "KEPT": "сохранён файлом",
        "REFUSEDONE": "не принят ({0})",
        "STOPPED": "Строка перестала работать; остальное не отправлено.",
        "ABORTED": "Остановлено. Строка закрыта; больше ничего не отправляется.",
        "DONE": "Готово: отправлено {0}, не принято {1}. На компьютере ничего не осталось: временная папка удалена, ничего не работает. Окно можно закрыть.",
        "ASKTOKEN": "Вставьте ключ с главной страницы мозга (imp_...)",
        "LOOKONLY": "Только посмотрел: ничего не отправлено и ничего не сохранено.",
        "WAITBRAIN": "  мозг занят чтением; ещё раз через {0} с",
        "REFUSEDBY": "Не принято, по причинам: {0}.",
        "REASON_too_big": "слишком большой", "REASON_type": "тип, который Знания не читают", "REASON_busy": "мозг занят",
        "REASON_gone": "его уже нет на компьютере", "REASON_other": "другое",
        "RETRYASK": "{0} из них можно отправить ещё раз. Нажмите Return здесь или «Отправить ещё раз» на главной странице мозга (жду 10 минут).",
        "RETRYING": "Отправляю {0} ещё раз.",
    },
}


def _sh_q(s: str) -> str:
    return "'" + s.replace("'", "'\\''") + "'"


def _ps_q(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def _sh_words(lang: str) -> str:
    out = []
    for k, v in WORDS[lang].items():
        v = v.replace("%", "%%")
        v = re.sub(r"\{\d\}", "%s", v)
        out.append(f"W_{k}={_sh_q(v)}")
    return "\n".join(out)


def _ps_words(lang: str) -> str:
    return "\n".join(f"    {k} = {_ps_q(v)}" for k, v in WORDS[lang].items())


def base_from(headers) -> str | None:
    """The brain's address as the person reached it: https://<Host>/api/bf. Behind the console's own
    proxy the api sees an internal Host (no dot, e.g. api:8000) and takes X-Forwarded-Host, which that
    proxy sets. A loopback Host (a test, or the api reached directly on the box) is http, no prefix.
    None when the host is not a plain host name."""
    host = (headers.get("host") or "").strip()
    name = host.split(":")[0]
    if name not in LOOPBACK and "." not in name:
        host = (headers.get("x-forwarded-host") or "").split(",")[0].strip()
        name = host.split(":")[0]
    if not host or not HOST_RE.match(host):
        return None
    if name in LOOPBACK:
        return f"http://{host}"
    return f"https://{host}{PREFIX}"


def render(kind: str, base: str, lang: str = "en") -> str:
    """The agent script with the brain's address, the words and the never-send rules filled in."""
    if kind not in TEMPLATES:
        raise ValueError("kind is sh or ps1")
    lang = lang if lang in WORDS else "en"
    r = rules()
    text = TEMPLATES[kind].read_text(encoding="utf-8")
    if kind == "sh":
        fill = {
            "BASE": base, "LANG": lang, "WORDS": _sh_words(lang),
            "SKIP_DIRS": " ".join(_sh_q(d) for d in r["skip_dirs"]),
            "DIR_SUFFIXES": " ".join(_sh_q(d) for d in r["dir_suffixes"]),
            "SECRET_RE": r["secret_re"].replace("'", "'\\''"),
            "HISTORY": " ".join(_sh_q(f"{label}|{sub}|{depth}") for label, sub, depth in r["history"]),
        }
    else:
        fill = {
            "BASE": base, "LANG": lang, "WORDS": _ps_words(lang),
            "SKIP_DIRS": ", ".join(_ps_q(d) for d in r["skip_dirs"]),
            "DIR_SUFFIXES": ", ".join(_ps_q(d) for d in r["dir_suffixes"]),
            "SKIP_FILES": ", ".join(_ps_q(p) for p in r["skip_files"]),
            "HISTORY": ", ".join(f"@{{ label = {_ps_q(label)}; sub = {_ps_q(sub.replace('/', chr(92)))}; depth = {depth} }}"
                                 for label, sub, depth in r["history"]),
        }
    fill.update({"READABLE": " ".join(r["readable"]), "AUDIO": " ".join(r["audio"]), "IMAGES": " ".join(r["images"]),
                 "MAX_FILE": str(r["max_file"]), "MAX_AUDIO": str(r["max_audio"]), "MAX_ENTRIES": str(r["max_entries"]),
                 "HISTORY_EXT": r["history_ext"]})
    for k, v in fill.items():
        text = text.replace(f"@@{k}@@", v)
    left = re.findall(r"@@[A-Z_]+@@", text)
    if left:
        raise ValueError(f"unfilled: {left}")
    return text


def lines_form(state: str, take: dict | None) -> str:
    """GET /documents/import-laptop/check?form=lines, for the shell agents (no JSON parser on a Mac's
    bash): 'state <none|waiting|chosen|folder|retry>', then one '<kind>\\t<path>' per chosen file (on
    'retry', IMPORT-PACE-1: only the refused files the owner asked to send again)."""
    out = [f"state {state}"]
    for p, kind in (take or {}).get("paths") or []:
        if "\t" in p or "\n" in p or "\r" in p:
            continue  # the agents never list such a name; never echo one
        out.append(f"{kind}\t{p}")
    return "\n".join(out) + "\n"
