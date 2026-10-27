"""cc_campaign: a campaign day as a feature of every brain (cc-job campaign ...). Created 2026-10-27.

A campaign is one sitting of parallel jobs: a charter (goal, rules, money caps the owner fills),
one brief per job, one report per lane, a pre-registration before the work and a scoring pass after
it. Everything lives in one folder on the desk, so the owner opens one place at the end.

    cc-job campaign new <name> [--date YYYY-MM-DD]    the folder, a dated charter, briefs/, reports/
    cc-job campaign lanes [--write]                   the lane table from the briefs (--write: into the charter)
    cc-job campaign launch [--only JOB]               one job per brief, the report path set; skips launched ones
    cc-job campaign status                            per lane: running or done, report present, owner-minutes
    cc-job campaign close [--in 30m | --at HH:MM]     schedules the scoring pass; no launch after it
    every verb takes --campaign <name or folder>; without it, the newest open campaign

Folder: <desk>/campaigns/<date>_<name>/ with CHARTER.md, REPORT-CONTRACT.md, briefs/, reports/,
templates/ (brief, pre-registration, scoring pass), spend.tsv (outside spend, one line before each
paid step), launched/ (the prompt and output of each job) and campaign.json (job ids).
The desk is ~/out unless CC_CAMPAIGN_ROOT says otherwise. Templates: templates/campaign/ in the
repo, or CC_CAMPAIGN_TEMPLATES. Standard library only; the launcher and the job lookup are passed
in by cc-job, so this module never talks to the bridge itself (tests stub both).
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import re
import shlex
import time
from pathlib import Path
from typing import Callable

HOME = Path(os.environ.get("HOME") or Path.home())
LANES_START, LANES_END = "<!-- lanes:start -->", "<!-- lanes:end -->"
# Fields the owner fills before anything launches: the goal and the money caps.
OWNER_FIELDS = ("<one-line goal>", "<n>")
TEMPLATE_FILES = ("BRIEF.md", "PREREGISTER.md", "SCORE.md")


def root() -> Path:
    return Path(os.environ.get("CC_CAMPAIGN_ROOT") or HOME / "out" / "campaigns")


def templates_dir() -> Path:
    env = os.environ.get("CC_CAMPAIGN_TEMPLATES")
    for d in ([Path(env)] if env else []) + [Path(__file__).resolve().parents[2] / "templates" / "campaign",
                                             HOME / ".local" / "share" / "cc-campaign" / "templates"]:
        if (d / "CHARTER.md").is_file():
            return d
    raise FileNotFoundError("campaign templates not found (templates/campaign in the repo, or CC_CAMPAIGN_TEMPLATES)")


def slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s[:48] or "campaign"


def _render(text: str, d: Path, name: str, date: str) -> str:
    vals = {"name": name, "date": date, "dir": str(d), "charter": str(d / "CHARTER.md"),
            "briefs": str(d / "briefs"), "reports": str(d / "reports"), "contract": str(d / "REPORT-CONTRACT.md")}
    for k, v in vals.items():
        text = text.replace("{{" + k + "}}", v)
    return text


def _state(d: Path) -> dict:
    f = d / "campaign.json"
    return json.loads(f.read_text()) if f.is_file() else {"jobs": {}, "closed": None}


def _save(d: Path, st: dict) -> None:
    tmp = d / "campaign.json.tmp"
    tmp.write_text(json.dumps(st, indent=2) + "\n")
    tmp.replace(d / "campaign.json")


def new(name: str, date: str | None = None, base: Path | None = None) -> Path:
    date = date or _dt.date.today().isoformat()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        raise ValueError(f"date is YYYY-MM-DD, not {date!r}")
    d = (base or root()) / f"{date}_{slug(name)}"
    if d.exists():
        raise FileExistsError(f"{d} exists already; pick another name")
    t = templates_dir()
    for sub in ("briefs", "reports", "templates", "launched"):
        (d / sub).mkdir(parents=True)
    r = lambda f: _render((t / f).read_text(), d, name, date)  # noqa: E731
    (d / "CHARTER.md").write_text(r("CHARTER.md"))
    (d / "REPORT-CONTRACT.md").write_text(r("REPORT.md"))
    for f in TEMPLATE_FILES:
        (d / "templates" / f).write_text(r(f))
    (d / "briefs" / "preregister.md").write_text(r("PREREGISTER.md"))
    (d / "spend.tsv").write_text("time\tlane\titem\testimate\tactual\n")
    _save(d, {"name": name, "date": date, "created": time.time(), "jobs": {}, "closed": None})
    return d


def resolve(arg: str | None = None, base: Path | None = None) -> Path:
    base = base or root()
    if arg:
        for c in (Path(arg), base / arg):
            if (c / "campaign.json").is_file():
                return c
        hits = sorted(base.glob(f"*_{slug(arg)}"))
        if hits:
            return hits[-1]
        raise FileNotFoundError(f"no campaign {arg!r} under {base}")
    all_ = sorted(p.parent for p in base.glob("*/campaign.json"))
    if not all_:
        raise FileNotFoundError(f"no campaign under {base}; start one with: cc-job campaign new <name>")
    open_ = [p for p in all_ if not _state(p).get("closed")]
    return (open_ or all_)[-1]


# ---- briefs and the lane table ----

def parse_brief(text: str, fname: str) -> dict:
    m = re.search(r"lane:\s*([A-Za-z0-9][\w-]*),\s*job\s+([A-Za-z0-9][\w-]*)", text, re.I)
    lane, job = (m.group(1).upper(), m.group(2).upper()) if m else ("-", slug(Path(fname).stem).upper())
    m = re.search(r"^Owns:\s*(.+)$", text, re.M)
    owns = [p.strip().strip("`") for p in m.group(1).split(";") if p.strip()] if m else []
    num = lambda k: (lambda x: float(x.group(1)) if x else None)(re.search(rf"^{k}:\s*([0-9]+(?:\.[0-9]+)?)\s*$", text, re.M))  # noqa: E731
    return {"lane": lane, "job": job, "owns": owns, "cap": num("Cap"), "share": num("Share"),
            "brief": fname, "unfilled": "<LANE>" in text or "<JOB>" in text or not m}


def briefs(d: Path) -> list[dict]:
    out = []
    for f in sorted((d / "briefs").glob("*.md")):
        if not f.name.startswith(("_", ".")):
            out.append(parse_brief(f.read_text(), f.name))
    return out


def _norm(p: str) -> str:
    return p.rstrip("/*").rstrip("/") + "/"


def overlaps(bs: list[dict]) -> list[str]:
    """Two different lanes owning one path, or one inside the other: a collision waiting to happen."""
    seen, out = [], []
    for b in bs:
        for p in b["owns"]:
            for lane, q in seen:
                if lane != b["lane"] and (_norm(p).startswith(_norm(q)) or _norm(q).startswith(_norm(p))):
                    out.append(f"{lane} owns {q} and {b['lane']} owns {p}")
            seen.append((b["lane"], p))
    return out


def _fmt(x: float | None) -> str:
    return "-" if x is None else (str(int(x)) if x == int(x) else str(x))


def lanes_table(d: Path) -> str:
    rows = ["| lane | job | owns | cap | outside share | brief |", "|---|---|---|---|---|---|"]
    for b in briefs(d):
        owns = " ; ".join(b["owns"]) if b["owns"] else "(no Owns: line: add one before launch)"
        rows.append(f"| {b['lane']} | {b['job']} | {owns} | {_fmt(b['cap'])} | {_fmt(b['share'] or 0)} | briefs/{b['brief']} |")
    return "\n".join(rows)


def write_lanes(d: Path) -> None:
    f = d / "CHARTER.md"
    text = f.read_text()
    if LANES_START not in text or LANES_END not in text:
        raise ValueError(f"{f} has no {LANES_START} ... {LANES_END} markers")
    head, rest = text.split(LANES_START, 1)
    tail = rest.split(LANES_END, 1)[1]
    f.write_text(f"{head}{LANES_START}\n{lanes_table(d)}\n{LANES_END}{tail}")


# ---- launch, status, close ----

def charter_gaps(d: Path) -> list[str]:
    text = (d / "CHARTER.md").read_text()
    return [m for m in OWNER_FIELDS if m in text]


def charter_cap(d: Path) -> float | None:
    m = re.search(r"^\|\s*per job[^|]*\|\s*([0-9]+(?:\.[0-9]+)?)\s*\|", (d / "CHARTER.md").read_text(), re.M)
    return float(m.group(1)) if m else None


def _command(d: Path, prompt: Path, out: Path, cap: float | None, wait: int = 0) -> str:
    reasoner = os.environ.get("CC_CAMPAIGN_REASONER", "claude -p --output-format text")
    capf = f" --max-budget-usd {_fmt(cap)}" if cap else ""
    q = shlex.quote
    cmd = f'{reasoner}{capf} --add-dir {q(str(d))} -- "$(cat {q(str(prompt))})" > {q(str(out))} 2>&1; chmod g+r {q(str(out))}'
    return f"sleep {int(wait)} && {cmd}" if wait > 0 else cmd


def report_path(d: Path, b: dict) -> Path:
    """One report per lane; the scoring pass writes SCORE.md."""
    name = "SCORE" if b["job"] == "SCORE-1" else (b["lane"] if b["lane"] != "-" else b["job"])
    return d / "reports" / f"{name}.md"


def _prompt(d: Path, st: dict, b: dict, text: str) -> str:
    report = report_path(d, b)
    return (f"Campaign {st.get('name', d.name)}. Charter: {d / 'CHARTER.md'} (read it first). "
            f"Your report: {report}, following {d / 'REPORT-CONTRACT.md'}. "
            f"Outside spend log: {d / 'spend.tsv'}.\n\n{text}")


StartFn = Callable[[str, str | None, str], dict]
GetFn = Callable[[str], dict]


def _start(d: Path, st: dict, b: dict, text: str, start: StartFn, cwd: str | None, wait: int = 0) -> dict:
    prompt = d / "launched" / f"{b['job']}.md"
    out = d / "launched" / f"{b['job']}.out"
    prompt.write_text(_prompt(d, st, b, text))
    cap = b["cap"] if b["cap"] is not None else charter_cap(d)
    try:
        return start(_command(d, prompt, out, cap, wait), cwd, f"{b['job']} {b['lane']}: campaign {st.get('name', d.name)}") or {"error": "no answer"}
    except Exception as e:  # noqa: BLE001
        return {"error": f"the bridge did not answer ({type(e).__name__})"}


def launch(d: Path, start: StartFn, only: str | None = None, cwd: str | None = None) -> tuple[int, list[str]]:
    st, lines = _state(d), []
    if st.get("closed"):
        return 1, ["closed: the scoring pass is scheduled; start a new campaign for more work"]
    gaps = charter_gaps(d)
    if gaps:
        return 1, [f"the charter still has owner fields to fill: {', '.join(gaps)} (in {d / 'CHARTER.md'})"]
    bs = sorted(briefs(d), key=lambda b: b["job"] != "PREREG-1")  # the measurement starts first
    if only:
        bs = [b for b in bs if b["job"] == only.upper()]
        if not bs:
            return 1, [f"no brief with job {only.upper()} in {d / 'briefs'}"]
    if not bs:
        return 1, [f"no briefs in {d / 'briefs'}; write one per job from {d / 'templates' / 'BRIEF.md'}"]
    bad = [b["brief"] for b in bs if b["unfilled"]]
    if bad:
        return 1, ["briefs without a filled lane/job line and an Owns: line: " + ", ".join(bad)]
    clash = overlaps(briefs(d))
    if clash:
        return 1, ["lanes overlap; change a brief's Owns: line first:"] + [f"  {c}" for c in clash]
    rc = 0
    for b in bs:
        if b["job"] in st["jobs"]:
            lines.append(f"{b['job']}: already launched ({st['jobs'][b['job']]['id']})")
            continue
        r = _start(d, st, b, (d / "briefs" / b["brief"]).read_text(), start, cwd)
        if r.get("error"):
            lines.append(f"{b['job']}: refused: {r['error']}")
            rc = 1
            if str(r["error"]).startswith(("HALT", "the bridge did not answer")):
                break  # the kill switch, or no bridge: nothing more starts
            continue
        st["jobs"][b["job"]] = {"id": r["id"], "lane": b["lane"], "brief": b["brief"], "started": time.time()}
        _save(d, st)
        lines.append(f"{b['job']} ({b['lane']}): started {r['id']}")
    return rc, lines


def owner_minutes(report: Path) -> int | None:
    if not report.is_file():
        return None
    m = re.search(r"^##\s*Needs the owner\s*$(.*?)(?=^##\s|\Z)", report.read_text(), re.M | re.S | re.I)
    return sum(int(x) for x in re.findall(r"\((\d+)\s*min", m.group(1))) if m else 0


def _job_state(j: dict | None, get: GetFn) -> str:
    if not j:
        return "not launched"
    try:
        d = get(j["id"]) or {}
    except Exception:  # noqa: BLE001
        d = {}
    if not d or d.get("error"):
        return "unknown"
    if d.get("running"):
        return "running"
    return "done" if d.get("rc") == 0 else f"failed rc={d.get('rc')}"


def status(d: Path, get: GetFn) -> list[dict]:
    st, rows = _state(d), []
    for b in briefs(d) + ([{"lane": "MEASURE", "job": "SCORE-1", "brief": "(close)"}] if "SCORE-1" in st["jobs"] else []):
        rep = report_path(d, b)
        rows.append({"lane": b["lane"], "job": b["job"], "state": _job_state(st["jobs"].get(b["job"]), get),
                     "report": rep.is_file(), "minutes": owner_minutes(rep)})
    return rows


def parse_when(at: str | None, within: str | None, now: _dt.datetime | None = None) -> int:
    """Seconds to wait: --in 30m / 2h / 90s / 45 (minutes), or --at HH:MM on the box clock (next one)."""
    if within:
        m = re.fullmatch(r"(\d+)\s*([smh]?)", within.strip())
        if not m:
            raise ValueError(f"--in takes 90s, 30m or 2h, not {within!r}")
        return int(m.group(1)) * {"s": 1, "m": 60, "": 60, "h": 3600}[m.group(2)]
    if at:
        m = re.fullmatch(r"(\d{1,2}):(\d{2})", at.strip())
        if not m or int(m.group(1)) > 23 or int(m.group(2)) > 59:
            raise ValueError(f"--at takes HH:MM, not {at!r}")
        now = now or _dt.datetime.now()
        t = now.replace(hour=int(m.group(1)), minute=int(m.group(2)), second=0, microsecond=0)
        if t <= now:
            t += _dt.timedelta(days=1)
        return int((t - now).total_seconds())
    return 0


def close(d: Path, start: StartFn, wait: int = 0, cwd: str | None = None) -> tuple[int, list[str]]:
    st = _state(d)
    if st.get("closed"):
        return 1, [f"already closed: scoring pass {st['closed'].get('id')}"]
    src = d / "briefs" / "_score.md"
    if not src.is_file():
        src = d / "templates" / "SCORE.md"
    text = src.read_text()
    b = parse_brief(text, src.name)
    b.update(lane="MEASURE", job="SCORE-1")
    r = _start(d, st, b, text, start, cwd, wait)
    if r.get("error"):
        return 1, [f"scoring pass refused: {r['error']}"]
    st["jobs"]["SCORE-1"] = {"id": r["id"], "lane": "MEASURE", "brief": str(src.relative_to(d)), "started": time.time()}
    st["closed"] = {"id": r["id"], "at": time.time() + wait, "brief": str(src.relative_to(d))}
    _save(d, st)
    when = "now" if not wait else f"in {wait // 60} min"
    return 0, [f"scoring pass {r['id']} scheduled {when} from {src.relative_to(d)}; it writes reports/SCORE.md",
               "no further launch in this campaign"]


# ---- the CLI, called by cc-job ----

def main(argv: list[str], start: StartFn, get: GetFn) -> int:
    args, opts, i = [], {}, 0
    while i < len(argv):
        a = argv[i]
        if a in ("--campaign", "--date", "--only", "--in", "--at") and i + 1 < len(argv):
            opts[a[2:]], i = argv[i + 1], i + 2
        elif a.startswith("--"):
            opts[a[2:]], i = True, i + 1
        else:
            args.append(a); i += 1
    if not args:
        print(__doc__); return 2
    verb, cwd = args[0], os.environ.get("CC_WORLD_DIR") or None
    try:
        if verb == "new":
            if len(args) < 2:
                print("cc-job campaign new <name> [--date YYYY-MM-DD]"); return 2
            d = new(" ".join(args[1:]), opts.get("date"))
            print(f"campaign folder: {d}\n"
                  f"1. fill the goal and the money caps in {d / 'CHARTER.md'}\n"
                  f"2. one brief per job in {d / 'briefs'} (template {d / 'templates' / 'BRIEF.md'}); preregister.md is there already\n"
                  f"3. cc-job campaign lanes --write, then launch --only PREREG-1, then launch")
            return 0
        d = resolve(opts.get("campaign"))
        if verb == "lanes":
            print(lanes_table(d))
            for c in overlaps(briefs(d)):
                print(f"overlap: {c}")
            if opts.get("write"):
                write_lanes(d); print(f"written into {d / 'CHARTER.md'}")
            return 0
        if verb == "launch":
            rc, lines = launch(d, start, opts.get("only"), cwd)
            print("\n".join(lines)); return rc
        if verb == "status":
            rows = status(d, get)
            print(f"{d}{'  (closed)' if _state(d).get('closed') else ''}")
            for r in rows:
                mins = "-" if r["minutes"] is None else f"{r['minutes']} min owed"
                print(f"{r['lane']:12} {r['job']:12} {r['state']:14} {'report' if r['report'] else 'no report':10} {mins}")
            if not rows:
                print("no briefs yet")
            return 0
        if verb == "close":
            wait = parse_when(opts.get("at"), opts.get("in"))
            rc, lines = close(d, start, wait, cwd)
            print("\n".join(lines)); return rc
    except (FileNotFoundError, FileExistsError, ValueError) as e:
        print(f"campaign: {e}"); return 1
    print(__doc__); return 2
