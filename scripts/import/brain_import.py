#!/usr/bin/env python3
"""Bring files from this computer into your brain, folder by folder (2026-11-03).

Runs on YOUR computer (Mac, Windows, Linux), Python 3.8+ standard library only.
It lists the usual folders with sizes and file counts, asks per folder yes, no, or
"only these types", and sends only what you said yes to, over HTTPS, to your own
brain with a one-time token from your console. Every file waits on the Knowledge
page for your approval; nothing is remembered before that. A receipt is written next
to where you ran it. The brain never reaches into this computer.

Never sent, whatever you answer: hidden files and folders (.ssh, .gnupg, .aws, .env,
...), key and password files (id_rsa, *.pem, *.key, *.p12, *.kdbx, keychains,
1Password and other vault exports), system and app folders (Library, AppData,
node_modules, ...), and anything the brain cannot use (video, archives). Audio goes as files for the
music tools, not into Knowledge: with y on a folder named Music, or when named (wav,mp3).

  python3 brain_import.py --brain https://you.brainfoundry.ai --token imp_...
  python3 brain_import.py --dry-run            (only list, send nothing)

Whole computer (--survey, the line from your brain's home, 2026-11-16): it walks your whole home folder
and your cloud folders (iCloud Drive, Google Drive, Dropbox, OneDrive) with the same never-send rules,
and sends a LIST only (path, size, type, date; no content). Your brain's home shows a plan grouped by
your work areas; you say yes there. This window waits, then brings exactly what you chose and stops.
Nothing stays running on this computer afterwards and the brain cannot open anything here.
Docs: docs/IMPORT.md in brainfoundry-nous.
"""
import argparse
import fnmatch
import json
import mimetypes
import os
import secrets
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

VERSION = "0.2.0"

USUAL = ["Documents", "Desktop", "Downloads", "Music", "Pictures", "Movies", "Videos"]
PROJECT_NAMES = {"projects", "code", "dev", "developer", "src", "repos", "work", "github", "git", "sites"}

# Folders never entered (case-insensitive name match), besides every hidden folder.
SKIP_DIRS = {
    "library", "appdata", "application data", "applications", "program files", "program files (x86)",
    "windows", "system", "system32", "system volume information", "$recycle.bin", "recycler",
    "node_modules", "__pycache__", "venv", "env", "site-packages", "bower_components", "target",
    "build", "dist", "keychains", "1password", "bitwarden", "keepass", "keepassxc", "lastpass",
    "password-store", "passwords", "secrets", "credentials", "photos library.photoslibrary",
    # mail stores and browser profiles (2026-11-16): never listed, never sent
    "mail", "mailboxes", "thunderbird", "outlook files", "mozilla", "firefox", "chrome", "google chrome",
    "chromium", "brave-browser", "microsoft edge", "user data", "safari",
}
# Files never sent, besides every hidden file (.env, .netrc, .npmrc, .pgpass, ...).
SKIP_FILES = [
    "id_rsa*", "id_dsa*", "id_ecdsa*", "id_ed25519*", "*.pem", "*.key", "*.p12", "*.pfx", "*.jks",
    "*.keystore", "*.kdbx", "*.kdb", "*.keychain", "*.keychain-db", "*.1pux", "*.1pif", "*.opvault",
    "*.agilekeychain", "*.gpg", "*.pgp", "*.asc", "*.ovpn", "*.ppk", "*.tfstate", "*.sqlite", "*.db",
    "*.env", "env.*", "*credential*", "*password*", "*passwd*", "*secret*", "*token*", "*.wallet",
    "wallet.dat", "*seed*phrase*", "*recovery*code*", "*.cookies", "cookies*",
    "*.pst", "*.ost", "*.mbox", "*.emlx", "*.olm",
]
TEXT = {"txt", "md", "markdown", "rst", "org", "tex", "csv", "tsv", "json", "yaml", "yml", "toml",
        "xml", "html", "htm", "srt", "vtt", "log", "py", "js", "ts", "tsx", "jsx", "sh", "c", "h",
        "cpp", "rs", "go", "java", "rb", "swift", "kt", "m", "r", "jl", "sql", "ipynb"}
DOCS = {"pdf", "docx"}
IMAGES = {"png", "jpg", "jpeg", "gif", "webp", "tif", "tiff", "bmp"}
READABLE = TEXT | DOCS | IMAGES
DEFAULT_TYPES = TEXT | DOCS  # images go only when named: OCR is slow and photos are rarely notes
AUDIO = {"wav", "aif", "aiff", "mp3", "flac", "m4a", "ogg", "als", "mid", "midi"}
MAX_FILE_BYTES = 25 * 1024 ** 2
# Audio is not read into Knowledge: it is kept as files on the brain (~/in/<date>/import/) for
# the music tools. 'y' on a folder named Music brings it; elsewhere name the types (wav,mp3).
MAX_AUDIO_FILE_BYTES = 200 * 1024 ** 2
MUSIC_FOLDERS = {"music"}


def skip_dir(name):
    """Why a folder is never entered, or '' to enter it."""
    if name.startswith("."):
        return "hidden"
    low = name.lower()
    if low in SKIP_DIRS or low.endswith((".photoslibrary", ".app", ".bundle", ".framework")):
        return "system or secrets"
    return ""


def skip_file(name):
    """Why a file is never sent, or '' if it may be offered."""
    if name.startswith("."):
        return "hidden"
    low = name.lower()
    for pat in SKIP_FILES:
        if fnmatch.fnmatch(low, pat):
            return "secret"
    return ""


def ext_of(name):
    return name.rsplit(".", 1)[-1].lower() if "." in name else ""


def walk(root):
    """Yield (path, relpath-under-root, size, verdict); verdict '' means offerable."""
    root = Path(root)
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = sorted(d for d in dirnames if not skip_dir(d))
        for f in sorted(filenames):
            p = Path(dirpath) / f
            try:
                if p.is_symlink() or not p.is_file():
                    continue
                size = p.stat().st_size
            except OSError:
                continue
            why = skip_file(f)
            if not why:
                e = ext_of(f)
                if e not in READABLE and e not in AUDIO:
                    why = "not readable by Knowledge"
                elif size > (MAX_AUDIO_FILE_BYTES if e in AUDIO else MAX_FILE_BYTES):
                    why = "over 200 MB" if e in AUDIO else "over 25 MB"
                elif size == 0:
                    why = "empty"
            yield p, p.relative_to(root).as_posix(), size, why


def summarize(root):
    s = {"files": 0, "bytes": 0, "offer": 0, "offer_bytes": 0, "types": {}, "skipped": {}}
    for _p, _rel, size, why in walk(root):
        s["files"] += 1
        s["bytes"] += size
        if why:
            s["skipped"][why] = s["skipped"].get(why, 0) + 1
        else:
            e = ext_of(_rel)
            s["offer"] += 1
            s["offer_bytes"] += size
            s["types"][e] = s["types"].get(e, 0) + 1
    return s


def candidates(home):
    """The usual folders that exist, then project folders: a top-level folder named like
    one, or one holding a .git."""
    home = Path(home)
    out, seen = [], set()
    for name in USUAL:
        p = home / name
        if p.is_dir():
            out.append(p)
            seen.add(name.lower())
    try:
        entries = sorted(home.iterdir())
    except OSError:
        entries = []
    for p in entries:
        if not p.is_dir() or p.name.lower() in seen or skip_dir(p.name):
            continue
        if p.name.lower() in PROJECT_NAMES or (p / ".git").exists():
            out.append(p)
    return out


def human(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024


def parse_answer(ans, music=False):
    """'y' -> DEFAULT_TYPES (and audio for a Music folder), 'n' or '' -> None,
    'pdf,md' or 't:pdf,md' -> those types (readable or audio only)."""
    a = (ans or "").strip().lower()
    if a in ("y", "yes"):
        return set(DEFAULT_TYPES) | (AUDIO if music else set())
    if a in ("", "n", "no"):
        return None
    if a.startswith("t:"):
        a = a[2:]
    types = {t.strip().lstrip(".") for t in a.replace(" ", ",").split(",") if t.strip()}
    unknown = types - READABLE - AUDIO
    if unknown:
        raise ValueError("not readable by Knowledge: " + ", ".join(sorted(unknown)))
    return types or None


def plan(folder, types):
    """Files of folder to send for these types: list of (path, name-in-brain, size)."""
    return [(p, f"{folder.name}/{rel}", size) for p, rel, size, why in walk(folder)
            if not why and ext_of(rel) in types]


class Brain:
    def __init__(self, url, token):
        u = urllib.parse.urlparse(url.rstrip("/"))
        local = u.hostname in ("localhost", "127.0.0.1", "::1")
        if u.scheme != "https" and not local:
            raise SystemExit("the brain address must start with https://")
        self.base = url.rstrip("/")
        self.token = token
        self.ctx = ssl.create_default_context()

    def _req(self, method, path, body=None, headers=None):
        h = {"Authorization": f"Bearer {self.token}", "User-Agent": f"brain-import/{VERSION}"}
        h.update(headers or {})
        req = urllib.request.Request(self.base + path, data=body, headers=h, method=method)
        try:
            with urllib.request.urlopen(req, timeout=300, context=self.ctx) as r:
                return r.status, json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            try:
                detail = json.loads(e.read()).get("detail")
            except Exception:
                detail = e.reason
            return e.code, {"detail": detail}

    def check(self):
        return self._req("GET", "/documents/import-laptop/check")

    def inventory(self, inv):
        import gzip
        body = gzip.compress(json.dumps(inv, separators=(",", ":")).encode("utf-8"))
        return self._req("POST", "/documents/import-laptop/check", body,
                         {"Content-Type": "application/json", "Content-Encoding": "gzip"})

    def send(self, path, name, keep=""):
        boundary = "----brainimport" + secrets.token_hex(12)
        ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        data = path.read_bytes()
        parts = [
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"path\"\r\n\r\n".encode() + name.encode("utf-8") + b"\r\n",
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"keep\"\r\n\r\n{keep}\r\n".encode(),
            (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{_q(path.name)}\"\r\n"
             f"Content-Type: {ctype}\r\n\r\n").encode("utf-8") + data + b"\r\n",
            f"--{boundary}--\r\n".encode(),
        ]
        body = b"".join(parts)
        # IMPORT-PACE-1: a busy brain answers "wait" (503); the file goes again after 2, 4, 8 ... 60 s
        pause = 2
        for attempt in range(1, SEND_TRIES + 1):
            try:
                st, j = self._req("POST", "/documents/import-laptop/file", body,
                                  {"Content-Type": f"multipart/form-data; boundary={boundary}"})
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                st, j = 0, {"detail": f"no answer: {e}"}
            if st not in BUSY_CODES or attempt == SEND_TRIES:
                return st, j
            print(f"  your brain is busy reading; trying again in {pause} s", flush=True)
            time.sleep(pause)
            pause = min(60, pause * 2)
        return st, j

    def refused(self, rows):
        """IMPORT-PACE-1: the files this run could not bring, for the home's list by reason."""
        body = "\n".join(f"{r.get('status') or 0}\t{r['path']}" for r in rows).encode("utf-8")
        return self._req("POST", "/documents/import-laptop/refused", body, {"Content-Type": "text/plain"})

    def finish(self):
        return self._req("POST", "/documents/import-laptop/finish", b"")


SEND_TRIES = 8
BUSY_CODES = (0, 429, 502, 503, 504)


def _q(s):
    return s.replace("\\", "_").replace('"', "_").replace("\r", "_").replace("\n", "_")


def ask(prompt, answers, key):
    if answers is not None:
        return answers.get(key.lower(), "n")
    try:
        return input(prompt)
    except EOFError:
        return "n"


# ── Whole computer (--survey, 2026-11-16) ──

MAX_ENTRIES = 300000


def cloud_roots(home, system=None):
    """(label, folder) for the cloud folders this computer has mounted: iCloud Drive, Google Drive,
    Dropbox, OneDrive, Box. On a Mac most live under ~/Library (which the walk never enters)."""
    home = Path(home)
    system = system or sys.platform
    out = []
    icloud = home / "Library" / "Mobile Documents" / "com~apple~CloudDocs"
    if icloud.is_dir():
        out.append(("iCloud Drive", icloud))
    storage = home / "Library" / "CloudStorage"
    try:
        mounted = sorted(storage.iterdir()) if storage.is_dir() else []
    except OSError:
        mounted = []
    for p in mounted:
        low = p.name.lower()
        for pre, label in (("googledrive", "Google Drive"), ("dropbox", "Dropbox"), ("onedrive", "OneDrive"), ("box", "Box")):
            if low.startswith(pre) and p.is_dir():
                gd = p / "My Drive"
                out.append((label, gd if gd.is_dir() else p))
                break
    try:
        top = sorted(home.iterdir())
    except OSError:
        top = []
    for p in top:
        low = p.name.lower()
        if not p.is_dir() or p.is_symlink():
            continue
        if low in ("icloud drive", "iclouddrive"):
            out.append(("iCloud Drive", p))
        elif low in ("google drive", "my drive"):
            out.append(("Google Drive", p))
        elif low == "dropbox" or low.startswith("dropbox ("):
            out.append(("Dropbox", p))
        elif low == "onedrive" or low.startswith("onedrive - "):
            out.append(("OneDrive", p))
        elif low == "box":
            out.append(("Box", p))
    if system.startswith("win"):
        for letter in "DEFGHIJKLMNOPQRSTUVWXYZ":
            gd = Path(f"{letter}:/My Drive")
            try:
                if gd.is_dir():
                    out.append(("Google Drive", gd))
            except OSError:
                continue
    # one label per root; a second account gets "(2)"
    seen, uniq = {}, []
    for label, p in out:
        if any(p == q for _l, q in uniq):
            continue
        n = seen.get(label, 0) + 1
        seen[label] = n
        uniq.append((label if n == 1 else f"{label} ({n})", p))
    return uniq


# The local history of the coding agents (MEMBERS-11, 2026-11-23). Every walk skips hidden folders
# by rule, so these two are named roots, like the cloud folders: only their session files (.jsonl)
# are offered, the brain turns each into one conversation document. Nothing else under ~/.codex or
# ~/.claude is ever walked (auth.json, config, credentials, memory folders stay out).
# (label, path parts under the home, deepest offered file: parts of its path under the root; 0 any)
AGENT_HISTORY = [
    ("Codex history", (".codex", "sessions"), 0),            # sessions/YYYY/MM/DD/rollout-*.jsonl
    ("Claude Code history", (".claude", "projects"), 2),     # projects/<slug>/<session>.jsonl
]
HISTORY_EXT = "jsonl"


def history_roots(home):
    """(label, folder, depth) for the coding agents' history folders this computer has. No link is
    followed: the hidden folder and its history folder must both be real folders."""
    home = Path(home)
    out = []
    for label, parts, depth in AGENT_HISTORY:
        p, ok = home, True
        for part in parts:
            p = p / part
            if p.is_symlink() or not p.is_dir():
                ok = False
                break
        if ok:
            out.append((label, p, depth))
    return out


def history_verdict(name, rel, size, depth):
    """Why a file under a history root is not offered, or ''."""
    why = skip_file(name)
    if why:
        return why
    if ext_of(name) != HISTORY_EXT or (depth and rel.count("/") + 1 > depth):
        return "not a chat"
    if size > MAX_FILE_BYTES:
        return "over 25 MB"
    if size == 0:
        return "empty"
    return ""


def survey(home, extra=(), system=None, limit=MAX_ENTRIES):
    """The inventory: (rows [[name, size, mtime]], skipped {"<folder>: <why>": n}, places {name: path},
    roots [labels]). Names are 'Documents/x.pdf' under the home and 'iCloud Drive/x.pdf' in a cloud
    folder. Only offerable files are listed; what is never sent is only counted, never named.
    The coding agents' history comes last, 'Codex history/...' and 'Claude Code history/...'
    (session files only); roots ends with their labels after the cloud labels."""
    home = Path(home)
    clouds = cloud_roots(home, system) + [(Path(f).name, Path(f)) for f in extra]
    cloud_paths = {p.resolve() for _l, p in clouds}
    rows, skipped, places = [], {}, {}

    def add(label, root, rel, p, size, why):
        top = rel.split("/")[0] if "/" in rel else "(home)"
        key = f"{label}/{top}" if label else top
        if why:
            k = f"{key}: {why}"
            skipped[k] = skipped.get(k, 0) + 1
            return
        name = f"{label}/{rel}" if label else rel
        try:
            mtime = int(p.stat().st_mtime)
        except OSError:
            return
        rows.append([name, size, mtime])
        places[name] = p

    def walk_root(label, root, history=None):
        root = Path(root)
        for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
            dp = Path(dirpath)
            keep = []
            for d in sorted(dirnames):
                if skip_dir(d):
                    continue
                try:
                    if (dp / d).resolve() in cloud_paths and label == "":
                        continue  # walked as its own root
                except OSError:
                    continue
                keep.append(d)
            dirnames[:] = keep
            for f in sorted(filenames):
                if len(rows) >= limit:
                    return
                p = dp / f
                try:
                    if p.is_symlink() or not p.is_file():
                        continue
                    size = p.stat().st_size
                except OSError:
                    continue
                rel = p.relative_to(root).as_posix()
                if history is not None:
                    add(label, root, rel, p, size, history_verdict(f, rel, size, history))
                    continue
                why = skip_file(f)
                if not why:
                    e = ext_of(f)
                    if e not in READABLE and e not in AUDIO:
                        why = "not readable by Knowledge"
                    elif size > (MAX_AUDIO_FILE_BYTES if e in AUDIO else MAX_FILE_BYTES):
                        why = "over 200 MB" if e in AUDIO else "over 25 MB"
                    elif size == 0:
                        why = "empty"
                add(label, root, rel, p, size, why)

    walk_root("", home)
    for label, root in clouds:
        walk_root(label, root)
    hist = history_roots(home)
    for label, root, depth in hist:
        walk_root(label, root, depth)
    return rows, skipped, places, [label for label, _p in clouds] + [label for label, _p, _d in hist]


def survey_run(a, out=print):
    home = Path(a.home)
    brain = None
    if not a.dry_run:
        if not a.brain or not a.token:
            raise SystemExit("needs --brain and --token (or --dry-run to only look)")
        brain = Brain(a.brain, a.token)
        st, j = brain.check()
        if st != 200:
            raise SystemExit(f"the brain refused the token ({st}): {j.get('detail')}")
        if not j.get("survey"):
            raise SystemExit("this line is for the folder-by-folder import; run it without --survey")
        out(f"Connected to {a.brain}.")
    out("Looking through this computer (names, sizes and dates only; nothing is read or sent yet)...")
    t0 = time.time()
    rows, skipped, places, roots = survey(home, a.folder)
    hist = [label for label, _p, _d in history_roots(home)]
    clouds = [r for r in roots if r not in hist]
    total = sum(r[1] for r in rows)
    out(f"Found {len(rows)} files your brain can take ({human(total)}) in {time.time() - t0:.0f} s"
        + (f"; cloud folders: {', '.join(clouds)}" if clouds else "; no cloud folders found")
        + (f"; also {', '.join(hist)} (your sessions as conversations)" if hist else "") + ".")
    if skipped:
        out(f"Never sent: {sum(skipped.values())} files (keys, passwords, hidden, mail, browser, video, archives, too big).")
    receipt = {"version": VERSION, "brain": a.brain, "mode": "survey", "started": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
               "dry_run": a.dry_run, "listed": len(rows), "bytes": total, "clouds": clouds, "sent": [], "refused": []}
    if a.dry_run:
        areas = {}
        for name, size, _m in rows:
            k = name.split("/")[0]
            areas[k] = areas.get(k, 0) + 1
        for k, n in sorted(areas.items(), key=lambda x: -x[1])[:30]:
            out(f"  {k}: {n} files")
        receipt["would_list"] = len(rows)
        return _write_receipt(a, receipt, out)
    inv = {"version": VERSION, "os": sys.platform, "files": rows, "skipped": skipped, "roots": roots}
    st, j = brain.inventory(inv)
    if st != 200:
        raise SystemExit(f"the brain did not take the list ({st}): {j.get('detail')}")
    out(f"\nThe list is on your brain: {j.get('files')} files in {j.get('groups')} groups.")
    out("Open your brain's home in the browser and choose what to bring. This window waits (Ctrl+C stops it).")
    take = None
    while take is None:
        time.sleep(a.poll)
        try:
            st, j = brain.check()
        except OSError:
            continue
        if st == 401:
            out("The line expired or was closed on the brain before a choice; nothing was sent.")
            receipt["ended"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
            return _write_receipt(a, receipt, out)
        if st == 200 and j.get("plan") == "chosen":
            take = j.get("take") or {"paths": []}
    asked = take.get("paths") or []
    chosen = [(places[n], n, kind) for n, kind in asked if n in places]
    ignored = len(asked) - len(chosen)
    total = sum(p.stat().st_size for p, _n, _k in chosen if p.exists())
    out(f"\nYou chose {len(chosen)} files ({human(total)}). Sending now.")
    if ignored:
        out(f"({ignored} names the brain asked for were not on this list and are not sent.)")
    sent_bytes = 0
    for i, (p, name, kind) in enumerate(chosen, 1):
        keep = "file" if kind == "files" and ext_of(name) in IMAGES else ""
        try:
            size = p.stat().st_size
            st, j = brain.send(p, name, keep)
        except OSError as e:
            size, st, j = 0, 0, {"detail": str(e)}
        sent_bytes += size
        if st == 200:
            receipt["sent"].append({"path": name, "proposal_id": j.get("proposal_id"), "size": size, "kept_at": j.get("where")})
            mark = f"kept in {j['where']}" if j.get("where") else "ok"
        else:
            receipt["refused"].append({"path": name, "status": st, "detail": j.get("detail")})
            mark = f"refused ({st}: {j.get('detail')})"
        out(f"[{i}/{len(chosen)}] {human(sent_bytes)}/{human(total)}  {name}  {mark}")
        if st == 401:
            out("The line stopped working; the rest was not sent.")
            break
    if receipt["refused"]:
        by = {}
        for r in receipt["refused"]:
            k = {413: "too big", 415: "a type Knowledge does not read", 404: "no longer on this computer"}.get(
                r.get("status"), "brain busy" if r.get("status") in BUSY_CODES else "other")
            by[k] = by.get(k, 0) + 1
        out("Not taken, by reason: " + ", ".join(f"{k} {n}" for k, n in by.items()) + ".")
        try:
            brain.refused(receipt["refused"])
        except Exception:  # noqa: BLE001
            pass
    st, j = brain.finish()
    receipt["finished"] = j if st == 200 else {"status": st, "detail": j.get("detail")}
    receipt["ended"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    _write_receipt(a, receipt, out)
    out("Done. Nothing keeps running on this computer; you can close this window.")
    return receipt


def _write_receipt(a, receipt, out):
    rp = Path(a.receipt_dir) / f"brain-import-receipt-{time.strftime('%Y%m%d-%H%M%S')}.json"
    rp.write_text(json.dumps(receipt, indent=1), encoding="utf-8")
    out(f"Sent {len(receipt['sent'])}, refused {len(receipt['refused'])}. Receipt: {rp}")
    return receipt


def run(argv=None, out=print):
    ap = argparse.ArgumentParser(description="Bring files from this computer into your brain, folder by folder.")
    ap.add_argument("--brain", help="your brain's address, https://...")
    ap.add_argument("--token", help="the one-time import token from your console (Knowledge page)")
    ap.add_argument("--home", default=str(Path.home()), help="where to look (default: your home folder)")
    ap.add_argument("--folder", action="append", default=[], help="offer this folder too (repeatable)")
    ap.add_argument("--answers", help="answer without asking, e.g. 'documents=y,downloads=pdf,md;music=n' (';' between folders)")
    ap.add_argument("--dry-run", action="store_true", help="list what would go, send nothing")
    ap.add_argument("--receipt-dir", default=".", help="where the receipt is written (default: here)")
    ap.add_argument("--survey", action="store_true",
                    help="whole computer: send a list only, choose on your brain's home, then bring what you chose")
    ap.add_argument("--poll", type=float, default=3.0, help=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    # started by the spoke's door (SWITCH-1, 2026-11-16): the one-time token comes in the environment,
    # never on the command line, so another account on this computer cannot read it in the process list
    if not a.token and os.environ.get("BRAIN_IMPORT_TOKEN"):
        a.token = os.environ["BRAIN_IMPORT_TOKEN"].strip()
    if a.survey:
        return survey_run(a, out)

    answers = None
    if a.answers:
        answers = {}
        for item in a.answers.split(";"):
            if "=" in item:
                k, v = item.split("=", 1)
                answers[k.strip().lower()] = v.strip()

    brain = None
    if not a.dry_run:
        if not a.brain or not a.token:
            raise SystemExit("needs --brain and --token (or --dry-run to only look)")
        brain = Brain(a.brain, a.token)
        st, j = brain.check()
        if st != 200:
            raise SystemExit(f"the brain refused the token ({st}): {j.get('detail')}")
        out(f"Connected to {a.brain}. Token good for {j['max_files']} files, {human(j['max_bytes'])}.")

    folders = candidates(a.home) + [Path(f).expanduser().resolve() for f in a.folder]
    chosen = []
    out("\nFolders on this computer (only files your brain can read are offered):\n")
    for f in folders:
        s = summarize(f)
        kinds = ", ".join(f"{n} {e}" for e, n in sorted(s["types"].items(), key=lambda x: -x[1])[:6]) or "none"
        out(f"{f}\n  {s['files']} files, {human(s['bytes'])}; offerable {s['offer']} ({human(s['offer_bytes'])}): {kinds}")
        if s["skipped"]:
            out("  never sent: " + ", ".join(f"{n} {why}" for why, n in sorted(s["skipped"].items())))
        if not s["offer"]:
            continue
        while True:
            music = f.name.lower() in MUSIC_FOLDERS
            what = "music and documents" if music else "documents and text"
            ans = ask(f"  Bring it? [y]es ({what}) / [n]o / types, e.g. pdf,md,jpg,wav: ", answers, f.name)
            try:
                types = parse_answer(ans, music)
                break
            except ValueError as e:
                out("  " + str(e))
                if answers is not None:
                    types = None
                    break
        if types:
            files = plan(f, types)
            out(f"  -> {len(files)} files, {human(sum(x[2] for x in files))}")
            chosen += files

    total = sum(x[2] for x in chosen)
    out(f"\nChosen: {len(chosen)} files, {human(total)}.")
    receipt = {"version": VERSION, "brain": a.brain, "started": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
               "dry_run": a.dry_run, "chosen": len(chosen), "bytes": total, "sent": [], "refused": []}
    if chosen and not a.dry_run:
        if answers is None and ask("Send them now? [y/n]: ", None, "").strip().lower() not in ("y", "yes"):
            chosen = []
        sent_bytes = 0
        for i, (p, name, size) in enumerate(chosen, 1):
            try:
                st, j = brain.send(p, name)
            except OSError as e:
                st, j = 0, {"detail": str(e)}
            sent_bytes += size
            if st == 200:
                receipt["sent"].append({"path": name, "proposal_id": j.get("proposal_id"), "size": size,
                                        "kept_at": j.get("where")})
                mark = f"kept in {j['where']}" if j.get("where") else "ok"
            else:
                receipt["refused"].append({"path": name, "status": st, "detail": j.get("detail")})
                mark = f"refused ({st}: {j.get('detail')})"
            out(f"[{i}/{len(chosen)}] {human(sent_bytes)}/{human(total)}  {name}  {mark}")
            if st == 401:
                out("The token stopped working; the rest was not sent.")
                break
        st, j = brain.finish()
        receipt["finished"] = j if st == 200 else {"status": st, "detail": j.get("detail")}
    elif a.dry_run:
        receipt["would_send"] = [n for _p, n, _s in chosen]
    receipt["ended"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    rp = Path(a.receipt_dir) / f"brain-import-receipt-{time.strftime('%Y%m%d-%H%M%S')}.json"
    rp.write_text(json.dumps(receipt, indent=1), encoding="utf-8")
    out(f"\nSent {len(receipt['sent'])}, refused {len(receipt['refused'])}. Receipt: {rp}")
    if any(x.get("proposal_id") for x in receipt["sent"]):
        out("Documents wait on your brain's Knowledge page (/upload) for your approval.")
    if any(x.get("kept_at") for x in receipt["sent"]):
        out("Music is kept as files on your brain under in/<date>/import/, listed in audio.tsv for the music tools.")
    return receipt


if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        print("\nStopped. Nothing more is sent.")
        sys.exit(130)
