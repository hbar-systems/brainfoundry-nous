"""The whole-computer survey, brain side (MOVE-IN-2, hbar 2026-11-16, docs/IMPORT.md "Whole computer").

The helper (scripts/import/brain_import.py --survey) walks the person's whole home folder and their
mounted cloud folders on their own computer, keeps the never-send rules there, and sends an INVENTORY
only: for each offerable file its path, size, type and modified time, plus per-folder counts of what is
never sent. No file content. It sends it under the same one-time import token as the folder-by-folder
run (POST /documents/import-laptop/check), then waits on that path for the person's choice.

Here the inventory becomes a plan: the files grouped into the person's work areas (by folder, type and
recency), each group with what the brain proposes for it:
- "knowledge": documents and text, read into Knowledge (each file a PENDING proposal, one yes later);
- "files": music and pictures, kept as files in the member's in/<date>/import/ (never remembered);
- "leave": stays on the computer (code with its own git, old downloads, too much at once), with why.
The console's home shows the plan; the owner says yes per group or "bring all proposed"
(POST /documents/import-laptop/plan, owner key). The helper, still running, reads the chosen paths
back (GET /documents/import-laptop/check) and pulls only those that are in its own inventory.
The brain never names a file the helper did not offer; the helper never sends one it did not list.
"""
import json
import os
import re
import threading
import time
from pathlib import Path, PurePosixPath

from api import laptop_import as li

# A survey run carries larger caps than a folder-by-folder run (the whole computer in one sitting).
SURVEY_TTL_SECONDS = 6 * 3600
SURVEY_MAX_FILES = 20000
SURVEY_MAX_BYTES = 20 * 1024 ** 3
# A member on a shared box (LAPTOP_AUDIO_HOST_DIR set: friends-1) has a 15 GB disk quota
# (docs/MEMBER_LIMITS.md): half of it per run. LAPTOP_SURVEY_MAX_GB overrides both.
SURVEY_MAX_BYTES_SHARED = 8 * 1024 ** 3


def survey_max_bytes(env: dict, free_bytes: int | None, total_bytes: int | None) -> int:
    """The byte cap of one survey run: 20 GB on a brain's own box, 8 GB for a member on a shared box,
    LAPTOP_SURVEY_MAX_GB when set; never more than the free disk less a tenth of the disk."""
    cap = SURVEY_MAX_BYTES_SHARED if env.get("LAPTOP_AUDIO_HOST_DIR") else SURVEY_MAX_BYTES
    try:
        if env.get("LAPTOP_SURVEY_MAX_GB"):
            cap = int(float(env["LAPTOP_SURVEY_MAX_GB"]) * 1024 ** 3)
    except ValueError:
        pass
    if free_bytes is not None and total_bytes:
        cap = min(cap, max(0, free_bytes - total_bytes // 10))
    return max(cap, 0)
# The inventory itself: at most this many file rows, and this many bytes of (decompressed) JSON.
MAX_ENTRIES = 300000
MAX_INVENTORY_BYTES = 64 * 1024 ** 2

KNOWLEDGE_EXT = li.TEXT_EXT | li.DOC_EXT
FILE_EXT = li.AUDIO_EXT | li.IMAGE_EXT
CODE_EXT = {"py", "js", "ts", "tsx", "jsx", "sh", "c", "h", "cpp", "rs", "go", "java", "rb", "swift",
            "kt", "m", "r", "jl", "sql", "ipynb", "json", "yaml", "yml", "toml", "xml", "html", "htm"}
YEAR = 365 * 86400
# Downloads older than this stay on the computer unless the person says yes.
OLD_DOWNLOADS = 2 * YEAR
# A knowledge group bigger than this is split by its next folder level, so one yes stays readable.
SPLIT_FILES = 400
# A code group (mostly code files) of more than this many files stays: it has its own git.
CODE_LEAVE_FILES = 150
# Pictures beyond this many in one group: kept as files only when the person says yes.
PICTURES_PROPOSE_MAX = 2000

CLOUD_ROOTS = ("iCloud Drive", "Google Drive", "Dropbox", "OneDrive", "Box")


def _area(parts):
    """The first folder of a path, with the cloud root kept in front ("Google Drive/Work")."""
    if len(parts) > 2 and parts[0] in CLOUD_ROOTS:
        return f"{parts[0]}/{parts[1]}"
    return parts[0] if len(parts) > 1 else "(home)"


def _kind(ext):
    if ext in KNOWLEDGE_EXT:
        return "knowledge"
    if ext in FILE_EXT:
        return "files"
    return ""


def validate(inv: dict) -> dict:
    """The helper's inventory, checked: every path relative and clean, sizes and times numbers,
    types the brain knows. Raises ValueError with a message for the helper."""
    if not isinstance(inv, dict) or not isinstance(inv.get("files"), list):
        raise ValueError("inventory must be an object with a files list")
    rows = inv["files"]
    if len(rows) > MAX_ENTRIES:
        raise ValueError(f"inventory over {MAX_ENTRIES} files")
    out = []
    for r in rows:
        if not isinstance(r, list) or len(r) < 3:
            raise ValueError("each file is [path, size, modified]")
        path, size, mtime = r[0], r[1], r[2]
        if not isinstance(path, str) or not isinstance(size, int) or not isinstance(mtime, (int, float)):
            raise ValueError("each file is [path, size, modified]")
        rel = li.clean_relpath(path)
        ext = li.extension(rel)
        if not _kind(ext) or size <= 0 or size > li.max_file_bytes(ext):
            continue  # the helper should not have listed it; it is simply not offered
        out.append((rel, size, int(mtime)))
    skipped = {}
    for k, v in (inv.get("skipped") or {}).items():
        if isinstance(k, str) and isinstance(v, int) and len(k) <= 200:
            skipped[k[:200]] = v
    roots = [x for x in (inv.get("roots") or []) if isinstance(x, str)][:40]
    return {"files": out, "skipped": skipped, "roots": roots,
            "helper": str(inv.get("version") or "")[:20], "os": str(inv.get("os") or "")[:20]}


def _group_key(parts, kind, split_at):
    area = _area(parts)
    depth = len(area.split("/"))
    if split_at and area in split_at and len(parts) > depth + 1:
        return f"{area}/{parts[depth]}", kind
    return area, kind


def plan(inv: dict, now: float | None = None) -> list:
    """Groups of the validated inventory, largest first, each with what the brain proposes.
    Group: id, folder, kind (knowledge|files), files, bytes, types (top 6), newest (epoch),
    proposal (knowledge|files|leave), why (one short reason key), paths (kept server side)."""
    now = now or time.time()
    files = inv["files"]
    # first pass: areas with many knowledge files are split one folder deeper
    count = {}
    for rel, _s, _m in files:
        parts = PurePosixPath(rel).parts
        if _kind(li.extension(rel)) == "knowledge":
            a = _area(parts)
            count[a] = count.get(a, 0) + 1
    split_at = {a for a, n in count.items() if n > SPLIT_FILES}
    groups = {}
    for rel, size, mtime in files:
        parts = PurePosixPath(rel).parts
        ext = li.extension(rel)
        kind = _kind(ext)
        key = _group_key(parts, kind, split_at if kind == "knowledge" else set())
        g = groups.get(key)
        if g is None:
            g = groups[key] = {"folder": key[0], "kind": kind, "files": 0, "bytes": 0, "types": {},
                               "newest": 0, "oldest": mtime, "code": 0, "paths": []}
        g["files"] += 1
        g["bytes"] += size
        g["types"][ext] = g["types"].get(ext, 0) + 1
        g["newest"] = max(g["newest"], mtime)
        g["oldest"] = min(g["oldest"], mtime)
        g["code"] += ext in CODE_EXT
        g["paths"].append(rel)
    out = []
    for (folder, kind), g in groups.items():
        top = folder.split("/")[0].lower()
        audio = sum(n for e, n in g["types"].items() if e in li.AUDIO_EXT)
        proposal, why = kind, "documents" if kind == "knowledge" else ("music" if audio * 2 >= g["files"] else "pictures")
        if kind == "knowledge":
            if g["code"] * 10 >= g["files"] * 8 and g["files"] > CODE_LEAVE_FILES:
                proposal, why = "leave", "code"
            elif top == "downloads" and now - g["newest"] > OLD_DOWNLOADS:
                proposal, why = "leave", "old_downloads"
        else:
            if why == "pictures" and g["files"] > PICTURES_PROPOSE_MAX:
                proposal, why = "leave", "many_pictures"
            elif why == "pictures" and top in ("downloads", "desktop"):
                proposal, why = "leave", "screenshots"
        gid = re.sub(r"[^a-z0-9]+", "-", f"{folder}-{kind}".lower()).strip("-")[:80]
        types = sorted(g["types"].items(), key=lambda x: (-x[1], x[0]))[:6]
        out.append({"id": gid, "folder": folder, "kind": kind, "files": g["files"], "bytes": g["bytes"],
                    "types": [[e, n] for e, n in types], "newest": g["newest"], "oldest": g["oldest"],
                    "proposal": proposal, "why": why, "paths": sorted(g["paths"])})
    # unique ids (two folders that slug the same)
    seen = {}
    for g in out:
        n = seen.get(g["id"], 0)
        seen[g["id"]] = n + 1
        if n:
            g["id"] = f"{g['id']}-{n + 1}"
    order = {"knowledge": 0, "files": 1, "leave": 2}
    out.sort(key=lambda g: (order[g["proposal"]], -g["files"], g["folder"]))
    return out


def totals(groups: list, ids) -> dict:
    ids = set(ids)
    pick = [g for g in groups if g["id"] in ids]
    return {"groups": len(pick), "files": sum(g["files"] for g in pick), "bytes": sum(g["bytes"] for g in pick)}


def public(groups: list) -> list:
    """The plan as the console sees it: no path lists, only the group, its numbers and a few names."""
    out = []
    for g in groups:
        x = {k: v for k, v in g.items() if k != "paths"}
        x["sample"] = [p.split("/")[-1] for p in g["paths"][:3]]
        out.append(x)
    return out


class SurveyStore:
    """One survey per token, beside the token store: <dir>/<token hash>.json holds the inventory's
    plan (with its paths) and, once the owner chose, the chosen group ids. Mode 600."""

    def __init__(self, path: Path):
        self.dir = Path(path)
        self._lock = threading.Lock()

    def _file(self, token_hash: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{64}", token_hash or ""):
            raise ValueError("bad token hash")
        return self.dir / f"{token_hash}.json"

    def _write(self, p: Path, data: dict) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(data), encoding="utf-8")
        os.chmod(tmp, 0o600)
        os.replace(tmp, p)

    def put(self, token_hash: str, inv: dict, now: float | None = None) -> dict:
        now = now or time.time()
        groups = plan(inv, now)
        data = {"at": int(now), "groups": groups, "skipped": inv["skipped"], "roots": inv["roots"],
                "os": inv.get("os", ""), "chosen": None, "chosen_at": None}
        with self._lock:
            self._write(self._file(token_hash), data)
            self._prune(now)
        return data

    def get(self, token_hash: str) -> dict | None:
        try:
            return json.loads(self._file(token_hash).read_text(encoding="utf-8"))
        except (FileNotFoundError, ValueError):
            return None

    def choose(self, token_hash: str, ids, caps: dict) -> dict:
        """The owner's yes: these group ids (or 'proposed' for every group not proposed to leave).
        Refused (ValueError) when the choice is over the run's caps; the message says the numbers."""
        with self._lock:
            data = self.get(token_hash)
            if data is None:
                raise LookupError("no survey for this run yet")
            if ids == "proposed":
                ids = [g["id"] for g in data["groups"] if g["proposal"] != "leave"]
            known = {g["id"] for g in data["groups"]}
            ids = [i for i in ids if isinstance(i, str) and i in known]
            t = totals(data["groups"], ids)
            left_files = caps["max_files"] - caps["files"]
            left_bytes = caps["max_bytes"] - caps["bytes"]
            if t["files"] > left_files or t["bytes"] > left_bytes:
                raise ValueError(f"over this run's caps: {t['files']} files, {t['bytes']} bytes chosen; "
                                 f"{left_files} files, {left_bytes} bytes left")
            data["chosen"] = ids
            data["chosen_at"] = int(time.time())
            self._write(self._file(token_hash), data)
            return t

    def take(self, token_hash: str) -> dict | None:
        """For the helper: the chosen paths ([path, kind]) and their totals, or None while the owner has not chosen."""
        data = self.get(token_hash)
        if not data or data.get("chosen") is None:
            return None
        ids = set(data["chosen"])
        out = []
        for g in data["groups"]:
            if g["id"] in ids:
                out += [[p, g["kind"]] for p in g["paths"]]
        return {**totals(data["groups"], ids), "paths": out}

    def _prune(self, now: float) -> None:
        for p in self.dir.glob("*.json"):
            try:
                if now - p.stat().st_mtime > 86400:
                    p.unlink()
            except OSError:
                pass
