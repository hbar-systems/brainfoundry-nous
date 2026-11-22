"""The campaign day (2026-10-27): scripts/cc/cc_campaign.py and cc-job campaign. No network; the launcher is a stub.

Run from repo root:
    pytest tests/test_cc_campaign.py -v
"""
from __future__ import annotations

import datetime as dt
import importlib.util
import json
import pathlib
import re
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name: str, file: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / "cc" / file)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


C = _load("cc_campaign", "cc_campaign.py")
JOB = _load("cc_job", "cc-job.py")


class Bridge:
    """Stands in for the bridge: records every start, answers job lookups from a table."""

    def __init__(self, refuse: str | None = None):
        self.started, self.jobs, self.refuse = [], {}, refuse

    def start(self, command, cwd, title):
        if self.refuse:
            return {"error": self.refuse}
        jid = f"J{len(self.started) + 1}"
        self.started.append({"id": jid, "command": command, "cwd": cwd, "title": title})
        self.jobs[jid] = {"id": jid, "running": True}
        return {"id": jid, "log": f"/tmp/{jid}.log"}

    def get(self, jid):
        return self.jobs.get(jid, {"error": "no such job"})


@pytest.fixture
def camp(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_CAMPAIGN_ROOT", str(tmp_path / "campaigns"))
    monkeypatch.delenv("CC_CAMPAIGN_TEMPLATES", raising=False)
    monkeypatch.delenv("CC_CAMPAIGN_REASONER", raising=False)
    monkeypatch.delenv("CC_WORLD_DIR", raising=False)
    return tmp_path / "campaigns"


def _fill_charter(d):
    f = d / "CHARTER.md"
    t = f.read_text().replace("<one-line goal>", "tidy the music library")
    t = re.sub(r"^(\| per job[^|]*\|)\s*<n>\s*\|", r"\1 5 |", t, flags=re.M)
    f.write_text(t.replace("<n>", "20"))


def _brief(d, name, lane, job, owns, extra=""):
    (d / "briefs" / name).write_text(f"Your lane: {lane}, job {job}.\nOwns: {owns}\n{extra}\nDo the work.\n")


def test_new_writes_the_folder_from_the_templates(camp):
    d = C.new("Music Library!", "2026-11-02")
    assert d == camp / "2026-11-02_music-library"
    for p in ("CHARTER.md", "REPORT-CONTRACT.md", "spend.tsv", "campaign.json", "briefs/preregister.md",
              "templates/BRIEF.md", "templates/PREREGISTER.md", "templates/SCORE.md"):
        assert (d / p).is_file(), p
    assert (d / "reports").is_dir() and (d / "launched").is_dir()
    charter = (d / "CHARTER.md").read_text()
    assert "created: 2026-11-02" in charter and str(d / "reports") in charter and "{{" not in charter
    assert C.LANES_START in charter and "<one-line goal>" in charter
    contract = (d / "REPORT-CONTRACT.md").read_text()
    for h in ("## Done", "## Verified, and how", "## Not verified", "## Needs the owner"):
        assert h in contract
    assert json.loads((d / "campaign.json").read_text())["name"] == "Music Library!"
    with pytest.raises(FileExistsError):
        C.new("music library", "2026-11-02")
    with pytest.raises(ValueError):
        C.new("x", "02.11.2026")


def test_templates_are_owner_neutral():
    """The template is public: no owner names, no box paths, no prices."""
    for f in (ROOT / "templates" / "campaign").glob("*.md"):
        t = f.read_text()
        assert not re.search(r"/home/|hbar|EUR|USD|\$\d", t), f.name


def test_parse_brief_and_lane_table(camp):
    d = C.new("t", "2026-11-02")
    _brief(d, "a.md", "music", "lib-1", "repos/lib ; out/music/", "Cap: 4\nShare: 10")
    (d / "briefs" / "_notes.md").write_text("never launched")
    (d / "briefs" / "b.md").write_text("no lane line here")
    bs = {b["job"]: b for b in C.briefs(d)}
    assert set(bs) == {"LIB-1", "B", "PREREG-1"}
    assert bs["LIB-1"]["lane"] == "MUSIC" and bs["LIB-1"]["owns"] == ["repos/lib", "out/music/"]
    assert bs["LIB-1"]["cap"] == 4 and bs["LIB-1"]["share"] == 10 and not bs["LIB-1"]["unfilled"]
    assert bs["B"]["unfilled"] and bs["PREREG-1"]["lane"] == "MEASURE"
    table = C.lanes_table(d)
    assert "| MUSIC | LIB-1 | repos/lib ; out/music/ | 4 | 10 | briefs/a.md |" in table
    assert "(no Owns: line" in table
    C.write_lanes(d)
    charter = (d / "CHARTER.md").read_text()
    assert "| MUSIC | LIB-1 |" in charter and "(no briefs yet)" not in charter
    C.write_lanes(d)                                  # idempotent: one table, not two
    assert charter == (d / "CHARTER.md").read_text()


def test_overlaps_between_lanes_only():
    bs = [{"lane": "A", "owns": ["repos/site/"]}, {"lane": "A", "owns": ["repos/site/docs"]},
          {"lane": "B", "owns": ["repos/site/docs/x.md"]}, {"lane": "C", "owns": ["repos/sitemap"]}]
    out = C.overlaps(bs)
    assert len(out) == 2 and all("B owns repos/site/docs/x.md" in o for o in out)


def test_launch_refuses_until_the_owner_fills_the_charter(camp):
    d = C.new("t", "2026-11-02")
    _brief(d, "a.md", "MUSIC", "LIB-1", "repos/lib")
    br = Bridge()
    rc, lines = C.launch(d, br.start)
    assert rc == 1 and "owner fields" in lines[0] and not br.started


def test_launch_refuses_unfilled_briefs_and_overlaps(camp):
    d = C.new("t", "2026-11-02")
    _fill_charter(d)
    (d / "briefs" / "x.md").write_text((d / "templates" / "BRIEF.md").read_text())
    br = Bridge()
    rc, lines = C.launch(d, br.start)
    assert rc == 1 and "x.md" in lines[0]
    (d / "briefs" / "x.md").unlink()
    _brief(d, "a.md", "MUSIC", "LIB-1", "repos/lib")
    _brief(d, "b.md", "SITE", "FRONT-1", "repos/lib/www")
    rc, lines = C.launch(d, br.start)
    assert rc == 1 and "overlap" in lines[0] and not br.started


def test_launch_one_job_per_brief_with_the_report_path(camp, monkeypatch):
    monkeypatch.setenv("CC_CAMPAIGN_REASONER", "reasoner -p")
    d = C.new("t", "2026-11-02")
    _fill_charter(d)
    _brief(d, "a.md", "MUSIC", "LIB-1", "repos/lib", "Cap: 3")
    _brief(d, "b.md", "SITE", "FRONT-1", "repos/site")
    br = Bridge()
    rc, lines = C.launch(d, br.start, only="prereg-1")
    assert rc == 0 and [s["title"].split()[0] for s in br.started] == ["PREREG-1"]
    rc, lines = C.launch(d, br.start, cwd="/w")
    assert rc == 0
    assert [s["title"].split()[0] for s in br.started] == ["PREREG-1", "LIB-1", "FRONT-1"]
    assert "PREREG-1: already launched (J1)" in lines
    lib = br.started[1]
    assert lib["command"].startswith("reasoner -p --max-budget-usd 3 ") and lib["cwd"] == "/w"
    assert "--max-budget-usd 5 " in br.started[2]["command"]          # the charter's per-job cap
    prompt = (d / "launched" / "LIB-1.md").read_text()
    assert str(d / "reports" / "MUSIC.md") in prompt and str(d / "CHARTER.md") in prompt
    assert prompt.endswith("Do the work.\n")
    st = json.loads((d / "campaign.json").read_text())
    assert st["jobs"]["LIB-1"]["id"] == "J2" and st["jobs"]["FRONT-1"]["lane"] == "SITE"
    rc, lines = C.launch(d, br.start)                 # nothing new: nothing started twice
    assert rc == 0 and len(br.started) == 3


def test_launch_stops_at_halt(camp):
    d = C.new("t", "2026-11-02")
    _fill_charter(d)
    _brief(d, "a.md", "MUSIC", "LIB-1", "repos/lib")
    rc, lines = C.launch(d, Bridge(refuse="HALT: owner stopped everything").start)
    assert rc == 1 and len(lines) == 1 and "HALT" in lines[0]
    assert json.loads((d / "campaign.json").read_text())["jobs"] == {}


def test_launch_stops_when_the_bridge_is_down(camp):
    d = C.new("t", "2026-11-02")
    _fill_charter(d)
    _brief(d, "a.md", "MUSIC", "LIB-1", "repos/lib")

    def down(*a):
        raise ConnectionRefusedError

    rc, lines = C.launch(d, down)
    assert rc == 1 and lines == ["PREREG-1: refused: the bridge did not answer (ConnectionRefusedError)"]


def test_status_running_done_report_minutes(camp):
    d = C.new("t", "2026-11-02")
    _fill_charter(d)
    _brief(d, "a.md", "MUSIC", "LIB-1", "repos/lib")
    _brief(d, "b.md", "SITE", "FRONT-1", "repos/site")
    _brief(d, "c.md", "TESTS", "MEND-1", "tests/")
    br = Bridge()
    C.launch(d, br.start, only="LIB-1")
    C.launch(d, br.start, only="FRONT-1")
    br.jobs["J1"] = {"running": False, "rc": 0}
    br.jobs["J2"] = {"running": False, "rc": 2}
    (d / "reports" / "MUSIC.md").write_text(
        "## Done\n- x\n## Needs the owner\n- listen to the loops (10 min): yes\n- pick a cover (5 min): one click\n")
    rows = {r["job"]: r for r in C.status(d, br.get)}
    assert rows["LIB-1"] == {"lane": "MUSIC", "job": "LIB-1", "state": "done", "report": True, "minutes": 15}
    assert rows["FRONT-1"]["state"] == "failed rc=2" and rows["FRONT-1"]["report"] is False
    assert rows["MEND-1"]["state"] == "not launched" and rows["PREREG-1"]["state"] == "not launched"
    br.jobs.clear()
    assert {r["job"]: r["state"] for r in C.status(d, br.get)}["LIB-1"] == "unknown"


def test_close_schedules_the_scoring_pass_once(camp):
    d = C.new("t", "2026-11-02")
    _fill_charter(d)
    _brief(d, "a.md", "MUSIC", "LIB-1", "repos/lib")
    br = Bridge()
    C.launch(d, br.start)
    rc, lines = C.close(d, br.start, wait=1800)
    assert rc == 0 and "in 30 min" in lines[0]
    score = br.started[-1]
    assert score["command"].startswith("sleep 1800 && ") and score["title"].startswith("SCORE-1 MEASURE")
    prompt = (d / "launched" / "SCORE-1.md").read_text()
    assert f"Your report: {d / 'reports' / 'SCORE.md'}," in prompt
    assert "waits on the owner" in prompt
    st = json.loads((d / "campaign.json").read_text())
    assert st["closed"]["id"] == score["id"] and st["closed"]["brief"] == "templates/SCORE.md"
    assert C.close(d, br.start)[0] == 1
    rc, lines = C.launch(d, br.start)
    assert rc == 1 and "closed" in lines[0]
    assert "SCORE-1" in {r["job"] for r in C.status(d, br.get)}


def test_close_prefers_the_reasoners_score_brief(camp):
    d = C.new("t", "2026-11-02")
    (d / "briefs" / "_score.md").write_text("Score it the special way.\n")
    br = Bridge()
    assert C.close(d, br.start)[0] == 0
    assert br.started[0]["command"].startswith("claude -p")
    assert (d / "launched" / "SCORE-1.md").read_text().endswith("Score it the special way.\n")


def test_parse_when():
    now = dt.datetime(2026, 11, 2, 17, 0)
    assert C.parse_when(None, None) == 0
    assert C.parse_when(None, "30m") == 1800 and C.parse_when(None, "2h") == 7200 and C.parse_when(None, "45") == 2700
    assert C.parse_when("18:30", None, now) == 5400
    assert C.parse_when("16:00", None, now) == 23 * 3600              # past: tomorrow
    for bad in (("25:00", None), (None, "soon")):
        with pytest.raises(ValueError):
            C.parse_when(*bad, now)


def test_resolve_newest_open(camp):
    a = C.new("first", "2026-11-01")
    b = C.new("second", "2026-11-02")
    assert C.resolve() == b and C.resolve("first") == a and C.resolve(str(a)) == a
    C.close(b, Bridge().start)
    assert C.resolve() == a
    with pytest.raises(FileNotFoundError):
        C.resolve("nothing")


def test_cc_job_routes_campaign_to_the_bridge(camp, monkeypatch, capsys):
    calls = []

    def fake_call(method, route, body=None, timeout=30):
        calls.append((method, route, body))
        return {"id": "J9", "log": "/tmp/J9.log"} if route == "/jobs/start" else {"running": True}

    monkeypatch.setattr(JOB, "_call", fake_call)
    monkeypatch.setattr(JOB, "cc_campaign", C)
    monkeypatch.setenv("CC_THREAD_ID", "th-1")
    assert JOB.main(["campaign", "new", "drill", "--date", "2026-11-03"]) == 0
    d = camp / "2026-11-03_drill"
    _fill_charter(d)
    _brief(d, "a.md", "MUSIC", "LIB-1", "repos/lib")
    assert JOB.main(["campaign", "lanes", "--write"]) == 0
    assert JOB.main(["campaign", "launch", "--only", "LIB-1"]) == 0
    assert calls[-1][1] == "/jobs/start" and calls[-1][2]["thread"] == "th-1" and calls[-1][2]["title"].startswith("LIB-1")
    assert JOB.main(["campaign", "status"]) == 0
    out = capsys.readouterr().out
    assert "| MUSIC | LIB-1 |" in out and re.search(r"MUSIC\s+LIB-1\s+running\s+no report", out)
    assert JOB.main(["campaign", "close", "--in", "10m"]) == 0
    assert calls[-1][2]["command"].startswith("sleep 600 && ")
    assert JOB.main(["campaign", "launch"]) == 1
    monkeypatch.setattr(JOB, "cc_campaign", None)
    assert JOB.main(["campaign", "status"]) == 1


def test_commands_pass_the_bridge_job_guard(camp):
    """The bridge runs every job command through cc_guard.check_job; launch and close must pass it."""
    G = _load("cc_guard", "cc_guard.py")
    d = C.new("t", "2026-11-02")
    _fill_charter(d)
    _brief(d, "a.md", "MUSIC", "LIB-1", "repos/lib")
    br = Bridge()
    C.launch(d, br.start)
    C.close(d, br.start, wait=60)
    for s in br.started:
        out = G.check_job(s["command"], "cards", "/tmp/settings.json")
        assert not isinstance(out, G.Refused), (s["title"], out)
        assert "claude --settings /tmp/settings.json -p" in out
