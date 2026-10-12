"""cc_recent (scripts/cc/cc_recent.py): the RECENT block, what moved in the last 48 h (2026-10-12).

The bridge puts it in front of the first turn of every new thread, and in front of any turn whose
whole message is the word "recap", inside a <recent> element, so a fresh thread starts where the
last ones left off. Five labelled parts, in this order, each one saying which file it came from:

  1. "Owed by hbar" from the newest ops/*_central-thread-map.md (first 12 lines of that section)
  2. the newest ops/*_idea-register.md: "3. Owed by hbar", "4. Agent queue" (10 lines each), last dated section
  3. ops/steward/queue.md: the repos under "Ready to push", one line each (name, ahead, leak result)
  4. the threads active in the last `hours` from threads.json in the bridge's state dir, newest first,
     each with the last thing the brain said in it (from the reasoner's own transcript jsonl);
     threads ruled finished in ops/threads/verdicts.tsv are left out, with a count at the end
  5. the memo tape: counts from in/memos/index.json

A missing source reads "(none)"; nothing here raises. Long ops lines are clipped to their gist
(the path is there for the rest); the five parts share max_chars, the longest trimmed first.
The composed block is cached for 120 s.
Standard library only; no network.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

CACHE_S = 120
_CACHE: dict = {}   # cache key -> (expires_at, block)
VERDICTS_REL = "ops/threads/verdicts.tsv"   # thread_id, verdict, date, note, source (2026-10-12)
VERDICTS_CACHE_S = 60
_VERDICTS_CACHE: dict = {}   # path -> (expires_at, verdicts)
VERDICTS = ("done", "let-go", "fold", "superseded", "continue", "keep")
FINISHED = frozenset(("done", "let-go", "fold", "superseded"))
MAX_THREADS = 12
SENTENCE_CHARS = 160
LINE_CHARS = 240   # an ops line beyond this is clipped to its gist
TAIL_BYTES = 256 * 1024   # how much of a transcript to read from its end for the last brain sentence


def project_slug(cwd: str | Path) -> str:
    """The reasoner's transcript folder name for a working directory (~/.claude/projects/<slug>):
    every character that is not a letter or digit becomes a dash (/home/hands/world -> -home-hands-world)."""
    return re.sub(r"[^A-Za-z0-9]", "-", str(cwd))


def recent_block(world_dir, state_dir, hours: int = 48, max_chars: int = 6000, *,
                 projects_dir=None, in_dir=None) -> str:
    """The block, as text. projects_dir is where the reasoner's transcripts are (default: this user's
    ~/.claude/projects/<slug of world_dir>); in_dir is the hands' inbox (default: beside world_dir)."""
    world = Path(world_dir) if world_dir else None
    projects = Path(projects_dir) if projects_dir else (Path.home() / ".claude" / "projects" / project_slug(world or ""))
    inbox = Path(in_dir) if in_dir else (world.parent / "in" if world else None)
    key = (str(world), str(state_dir), hours, max_chars, str(projects), str(inbox))
    hit = _CACHE.get(key)
    if hit and hit[0] > time.time():
        return hit[1]
    ops = world / "ops" if world else None
    cap = max(600, max_chars // 2)   # a loose cap per part; _fit shares the whole budget fairly
    parts = [
        _owed(ops, cap),
        _register(ops, cap),
        _ready_to_push(ops, cap),
        _threads(Path(state_dir) if state_dir else None, projects, hours, cap, load_verdicts(world)),
        _memos(inbox, cap),
    ]
    block = "\n\n".join(_fit(parts, max_chars))
    _CACHE[key] = (time.time() + CACHE_S, block)
    return block


# ------------------------------------------------------------------ parts ----
def _owed(ops: Path | None, cap: int) -> str:
    path = _newest(ops, "*_central-thread-map.md")
    head = f"## Owed by hbar ({_rel(path) if path else 'no ops/*_central-thread-map.md'})"
    if not path:
        return head + "\n(none)"
    lines = _section(_read(path), lambda h: h.lower().startswith("owed by hbar"), 12)
    return _clip(head + "\n" + ("\n".join(lines) if lines else "(none)"), cap)


def _register(ops: Path | None, cap: int) -> str:
    path = _newest(ops, "*_idea-register.md")
    head = f"## Idea register ({_rel(path) if path else 'no ops/*_idea-register.md'})"
    if not path:
        return head + "\n(none)"
    text = _read(path)
    out = [head]
    for label, want in (("3. Owed by hbar", "3. owed by hbar"), ("4. Agent queue", "4. agent queue")):
        lines = _section(text, lambda h, w=want: h.lower().startswith(w), 10)
        out.append(f"### {label}\n" + ("\n".join(lines) if lines else "(none)"))
    dated = [h for h in _headings(text) if re.match(r"\d{4}-\d{2}-\d{2}", h)]
    if dated:
        last = dated[-1]
        lines = _section(text, lambda h, w=last: h == w, 10)
        out.append(f"### {last}\n" + ("\n".join(lines) if lines else "(none)"))
    else:
        out.append("### last dated section\n(none)")
    return _clip("\n".join(out), cap)


_PUSH_LINE = re.compile(r"^###\s+(?P<name>.+?)\s*(?:\((?P<branch>[^)]*)\))?:\s*(?P<ahead>\d+)\s+commit\(s\)\s+ahead(?:,\s*(?P<behind>\d+)\s+behind)?;\s*leak check:\s*(?P<leak>.*)$")


def _ready_to_push(ops: Path | None, cap: int) -> str:
    path = ops / "steward" / "queue.md" if ops else None
    if not path or not path.is_file():
        return "## Ready to push (no ops/steward/queue.md)\n(none)"
    head = f"## Ready to push ({_rel(path)})"
    lines = []
    inside = False
    for raw in _read(path).splitlines():
        if raw.startswith("## "):
            inside = raw[3:].strip().lower().startswith("ready to push")
            continue
        if inside and raw.startswith("### "):
            m = _PUSH_LINE.match(raw.strip())
            if m:
                behind = f", {m['behind']} behind" if m["behind"] else ""
                lines.append(f"- {m['name']}: {m['ahead']} ahead{behind}; leak check: {m['leak'].strip()}")
            else:
                lines.append("- " + raw[4:].strip())
    return _clip(head + "\n" + ("\n".join(lines) if lines else "(none)"), cap)


def _threads(state_dir: Path | None, projects: Path, hours: int, cap: int, verdicts: dict | None = None) -> str:
    path = state_dir / "threads.json" if state_dir else None
    head = f"## Threads active in the last {hours} h ({path or 'no state dir'}; transcripts under {projects})"
    items = _json(path) if path else None
    if not isinstance(items, list):
        return head + "\n(none)"
    since = time.time() - hours * 3600
    live = []
    hidden = 0
    for th in items:
        if not isinstance(th, dict) or th.get("archived"):
            continue
        t = _when(th.get("last") or th.get("started"))
        if t is None or t < since:
            continue
        v = verdict_for(verdicts, th) if verdicts else None
        if v and v.get("verdict") in FINISHED:
            hidden += 1
            continue
        live.append((t, th))
    live.sort(key=lambda x: x[0], reverse=True)
    lines = []
    for t, th in live[:MAX_THREADS]:
        stamp = time.strftime("%Y-%m-%d %H:%MZ", time.gmtime(t))
        title = " ".join(str(th.get("title") or "(untitled)").split())[:80]
        said = _last_brain_sentence(projects / f"{th.get('claude')}.jsonl") if th.get("claude") else ""
        lines.append(f"- {title} ({stamp}): {said or '(no transcript)'}")
    if hidden:
        lines.append(f"{hidden} finished thread{'s' if hidden != 1 else ''} hidden ({VERDICTS_REL})")
    return _clip(head + "\n" + ("\n".join(lines) if lines else "(none)"), cap)


# ------------------------------------------------------------- verdicts ----
def load_verdicts(world_dir) -> dict:
    """The thread verdicts the central thread rules (2026-10-12): ops/threads/verdicts.tsv in the
    world, columns thread_id, verdict, date, note, source. Keyed by thread id as written and by its
    8-char prefix (the console's brain id or the reasoner's claude id, either one). A row
    with a blank id or a verdict outside VERDICTS is skipped; a later row for the same id wins.
    Cached 60 s per path; a missing or unreadable file is an empty dict. Never raises."""
    if not world_dir:
        return {}
    path = Path(world_dir) / VERDICTS_REL
    key = str(path)
    hit = _VERDICTS_CACHE.get(key)
    if hit and hit[0] > time.time():
        return hit[1]
    out: dict = {}
    for ln in _read(path).splitlines():
        if not ln.strip() or ln.startswith("#"):
            continue
        cols = [c.strip() for c in ln.split("\t")]
        if len(cols) < 2 or cols[0].lower() == "thread_id":
            continue
        tid = cols[0]
        verdict = cols[1].lower().replace(" ", "-").replace("_", "-")
        if verdict == "folded":
            verdict = "fold"
        if not tid or verdict not in VERDICTS:
            continue
        row = {"verdict": verdict, "verdict_date": cols[2] if len(cols) > 2 else "",
               "verdict_note": cols[3] if len(cols) > 3 else "", "verdict_source": cols[4] if len(cols) > 4 else ""}
        out[tid] = row
        out[tid[:8]] = row
    _VERDICTS_CACHE[key] = (time.time() + VERDICTS_CACHE_S, out)
    return out


def verdict_for(verdicts: dict, th: dict) -> dict | None:
    """The verdict row for one threads.json entry: by its brain id or its claude id, in full or by
    the 8-char prefix either side; None when the thread has no ruling."""
    if not verdicts or not isinstance(th, dict):
        return None
    for tid in (th.get("brain"), th.get("claude")):
        tid = str(tid or "").strip()
        if not tid:
            continue
        hit = verdicts.get(tid) or verdicts.get(tid[:8])
        if hit:
            return hit
    return None


def _memos(inbox: Path | None, cap: int) -> str:
    path = inbox / "memos" / "index.json" if inbox else None
    head = f"## Memo tape ({path or 'no inbox'})"
    data = _json(path) if path else None
    memos = (data or {}).get("memos") if isinstance(data, dict) else None
    if not isinstance(memos, list):
        return head + "\n(none)"
    pending = sum(1 for m in memos if isinstance(m, dict) and (m.get("stage") != "filed" or not m.get("review_done")))
    bits = sum(int(m.get("n_pending") or 0) for m in memos if isinstance(m, dict))
    held = sent = 0
    memos_dir = Path(str((data or {}).get("memos_dir") or (inbox / "memos")))
    for m in memos:
        if not isinstance(m, dict) or not m.get("id"):
            continue
        b = _json(memos_dir / str(m["id"]) / "bits.json")
        b = b.get("bits") if isinstance(b, dict) else b
        for x in b or []:
            st = ((x.get("dispatch") or {}).get("state") if isinstance(x, dict) else None)
            held += st == "held"
            sent += st == "sent"
    line = (f"{len(memos)} memos, {pending} pending signoff, {bits} bits pending, "
            f"dispatch held {held} / sent {sent}")
    return _clip(head + "\n" + line, cap)


# ---------------------------------------------------------------- helpers ----
def _newest(ops: Path | None, pattern: str) -> Path | None:
    """The newest dated file by name (ops files start with YYYY-MM-DD)."""
    if not ops or not ops.is_dir():
        return None
    files = sorted(p for p in ops.glob(pattern) if p.is_file())
    return files[-1] if files else None


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _rel(path: Path) -> str:
    """ops/<file> for the label, whatever the world is mounted as."""
    parts = path.parts
    return "/".join(parts[parts.index("ops"):]) if "ops" in parts else str(path)


def _headings(text: str) -> list[str]:
    return [ln.lstrip("#").strip() for ln in text.splitlines() if ln.startswith("#")]


def _section(text: str, match, n: int) -> list[str]:
    """The first n non-blank lines under the first heading (any level) that `match` accepts,
    up to the next heading of the same or a higher level."""
    lines = text.splitlines()
    for i, ln in enumerate(lines):
        if not ln.startswith("#"):
            continue
        level = len(ln) - len(ln.lstrip("#"))
        if not match(ln.lstrip("#").strip()):
            continue
        out = []
        for nxt in lines[i + 1:]:
            if nxt.startswith("#") and (len(nxt) - len(nxt.lstrip("#"))) <= level:
                break
            if nxt.strip():
                out.append(_gist(nxt))
                if len(out) >= n:
                    break
        return out
    return []


def _when(s) -> float | None:
    """Seconds since the epoch for an ISO-8601 UTC stamp like 2026-10-12T10:41:00Z; None otherwise."""
    if not isinstance(s, str):
        return None
    try:
        return time.mktime(time.strptime(s[:19], "%Y-%m-%dT%H:%M:%S")) - time.timezone
    except ValueError:
        return None


def _last_brain_sentence(path: Path) -> str:
    """The first SENTENCE_CHARS of the last assistant text block in a reasoner transcript (jsonl,
    one event per line). Reads only the tail of the file; a missing or odd file gives ''."""
    try:
        with path.open("rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - TAIL_BYTES))
            tail = f.read().decode("utf-8", errors="replace")
    except OSError:
        return ""
    for raw in reversed(tail.splitlines()):
        if '"assistant"' not in raw:
            continue
        try:
            ev = json.loads(raw)
        except ValueError:
            continue
        if ev.get("type") != "assistant":
            continue
        content = (ev.get("message") or {}).get("content")
        if isinstance(content, str):
            content = [{"type": "text", "text": content}]
        for c in reversed(content or []):
            if isinstance(c, dict) and c.get("type") == "text" and str(c.get("text") or "").strip():
                return " ".join(str(c["text"]).split())[:SENTENCE_CHARS]
    return ""


def _gist(line: str) -> str:
    line = line.rstrip()
    if len(line) <= LINE_CHARS:
        return line
    cut = line[: LINE_CHARS - 4]
    return (cut[: cut.rfind(" ")] if " " in cut else cut).rstrip() + " ..."


def _clip(text: str, n: int) -> str:
    return text if len(text) <= n else text[: max(0, n - 6)].rstrip() + "\n(cut)"


def _fit(parts: list[str], max_chars: int) -> list[str]:
    """Trim the parts to max_chars together (joined by blank lines), always the longest one first,
    so a short part never loses its line to a long one."""
    parts = list(parts)
    sep = 2 * (len(parts) - 1)
    while parts and sum(map(len, parts)) + sep > max_chars:
        i = max(range(len(parts)), key=lambda k: len(parts[k]))
        over = sum(map(len, parts)) + sep - max_chars
        second = sorted(map(len, parts))[-2] if len(parts) > 1 else 0
        parts[i] = _clip(parts[i], max(second - 1, len(parts[i]) - over, 0))
    return parts
