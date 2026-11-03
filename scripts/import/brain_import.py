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
node_modules, ...), and anything Knowledge cannot read (audio, video, archives).

  python3 brain_import.py --brain https://you.brainfoundry.ai --token imp_...
  python3 brain_import.py --dry-run            (only list, send nothing)
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

VERSION = "0.1.0"

USUAL = ["Documents", "Desktop", "Downloads", "Music", "Pictures", "Movies", "Videos"]
PROJECT_NAMES = {"projects", "code", "dev", "developer", "src", "repos", "work", "github", "git", "sites"}

# Folders never entered (case-insensitive name match), besides every hidden folder.
SKIP_DIRS = {
    "library", "appdata", "application data", "applications", "program files", "program files (x86)",
    "windows", "system", "system32", "system volume information", "$recycle.bin", "recycler",
    "node_modules", "__pycache__", "venv", "env", "site-packages", "bower_components", "target",
    "build", "dist", "keychains", "1password", "bitwarden", "keepass", "keepassxc", "lastpass",
    "password-store", "passwords", "secrets", "credentials", "photos library.photoslibrary",
}
# Files never sent, besides every hidden file (.env, .netrc, .npmrc, .pgpass, ...).
SKIP_FILES = [
    "id_rsa*", "id_dsa*", "id_ecdsa*", "id_ed25519*", "*.pem", "*.key", "*.p12", "*.pfx", "*.jks",
    "*.keystore", "*.kdbx", "*.kdb", "*.keychain", "*.keychain-db", "*.1pux", "*.1pif", "*.opvault",
    "*.agilekeychain", "*.gpg", "*.pgp", "*.asc", "*.ovpn", "*.ppk", "*.tfstate", "*.sqlite", "*.db",
    "*.env", "env.*", "*credential*", "*password*", "*passwd*", "*secret*", "*token*", "*.wallet",
    "wallet.dat", "*seed*phrase*", "*recovery*code*", "*.cookies", "cookies*",
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
                if e not in READABLE:
                    why = "audio (music kit)" if e in AUDIO else "not readable by Knowledge"
                elif size > MAX_FILE_BYTES:
                    why = "over 25 MB"
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


def parse_answer(ans):
    """'y' -> DEFAULT_TYPES, 'n' or '' -> None, 'pdf,md' or 't:pdf,md' -> those types (readable only)."""
    a = (ans or "").strip().lower()
    if a in ("y", "yes"):
        return set(DEFAULT_TYPES)
    if a in ("", "n", "no"):
        return None
    if a.startswith("t:"):
        a = a[2:]
    types = {t.strip().lstrip(".") for t in a.replace(" ", ",").split(",") if t.strip()}
    unknown = types - READABLE
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

    def send(self, path, name):
        boundary = "----brainimport" + secrets.token_hex(12)
        ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        data = path.read_bytes()
        parts = [
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"path\"\r\n\r\n".encode() + name.encode("utf-8") + b"\r\n",
            (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{_q(path.name)}\"\r\n"
             f"Content-Type: {ctype}\r\n\r\n").encode("utf-8") + data + b"\r\n",
            f"--{boundary}--\r\n".encode(),
        ]
        return self._req("POST", "/documents/import-laptop/file", b"".join(parts),
                         {"Content-Type": f"multipart/form-data; boundary={boundary}"})

    def finish(self):
        return self._req("POST", "/documents/import-laptop/finish", b"")


def _q(s):
    return s.replace("\\", "_").replace('"', "_").replace("\r", "_").replace("\n", "_")


def ask(prompt, answers, key):
    if answers is not None:
        return answers.get(key.lower(), "n")
    try:
        return input(prompt)
    except EOFError:
        return "n"


def run(argv=None, out=print):
    ap = argparse.ArgumentParser(description="Bring files from this computer into your brain, folder by folder.")
    ap.add_argument("--brain", help="your brain's address, https://...")
    ap.add_argument("--token", help="the one-time import token from your console (Knowledge page)")
    ap.add_argument("--home", default=str(Path.home()), help="where to look (default: your home folder)")
    ap.add_argument("--folder", action="append", default=[], help="offer this folder too (repeatable)")
    ap.add_argument("--answers", help="answer without asking, e.g. 'documents=y,downloads=pdf,md;music=n' (';' between folders)")
    ap.add_argument("--dry-run", action="store_true", help="list what would go, send nothing")
    ap.add_argument("--receipt-dir", default=".", help="where the receipt is written (default: here)")
    a = ap.parse_args(argv)

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
            ans = ask("  Bring it? [y]es (documents and text) / [n]o / types, e.g. pdf,md,jpg: ", answers, f.name)
            try:
                types = parse_answer(ans)
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
                receipt["sent"].append({"path": name, "proposal_id": j.get("proposal_id"), "size": size})
                mark = "ok"
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
    if receipt["sent"]:
        out("They wait on your brain's Knowledge page (/upload) for your approval.")
    return receipt


if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        print("\nStopped. Nothing more is sent.")
        sys.exit(130)
