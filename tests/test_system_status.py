"""The technical surface (api/system_status.py): thresholds and warning lines. Pure, no
docker, no database.

Run from repo root:
    pytest tests/test_system_status.py -v
"""
from __future__ import annotations

from api import system_status as s


def test_level_thresholds():
    assert s.level(50, 80, 90) == "ok" and s.level(85, 80, 90) == "warn" and s.level(95, 80, 90) == "alert"
    assert s.level(20, 15, 7, lower_is_worse=True) == "ok"
    assert s.level(10, 15, 7, lower_is_worse=True) == "warn"
    assert s.level(3, 15, 7, lower_is_worse=True) == "alert"


def test_warnings_name_each_crossed_threshold():
    rep = {"host": {"disk": {"level": "warn", "pct": 85.0, "free_gb": 12.0},
                    "memory": {"level": "ok"}, "load": {"level": "alert", "five": 9.0, "cores": 4}},
           "docker": {"not_running": ["brain-ui-1"], "reclaimable_gb": 12.5},
           "backups": {"level": "warn", "count": 3, "age_days": 3.0},
           "database": {"level": "ok"}}
    w = s.warnings(rep)
    assert w[0].startswith("disk 85.0%") and any("load 9.0" in x for x in w)
    assert any("not running: brain-ui-1" in x for x in w) and any("12.5 GB reclaimable" in x for x in w)
    assert any("last backup 3.0 days ago" in x for x in w) and len(w) == 5
    assert s.warnings({"host": {}, "docker": {}, "backups": {"level": "ok", "count": 1}, "database": {}}) == []


def test_size_parsing():
    assert s._to_gb("12.56GB") == 12.56 and abs(s._to_gb("500MB") - 0.5) < 1e-9 and s._to_gb("0B") == 0.0


def test_host_reads_this_machine(tmp_path):
    h = s.host(str(tmp_path))
    assert "disk" in h and 0 <= h["disk"]["pct"] <= 100 and h["disk"]["level"] in ("ok", "warn", "alert")


def test_dangling_sum_is_what_the_button_can_remove():
    assert s.dangling_gb("1.2GB\n500MB\n\n") == 1.7 and s.dangling_gb("") == 0.0


# ---------------------------------------------------- a shared box (2026-10-19) ----
# docs/MULTI_INSTANCE.md: several members' brains on one box. Docker and the host are stubbed.
import json  # noqa: E402

import pytest  # noqa: E402


def _ps(*rows):
    return "\n".join(json.dumps({"Names": n, "State": st, "Status": "Up", "Image": "img", "ID": i + "0" * (12 - len(i)),
                                 "Labels": f"com.docker.compose.project={p},com.docker.compose.service=x"}) for n, p, st, i in rows)


BOX = _ps(("brain-api-1", "brain", "running", "aaa"), ("brain-ollama-1", "brain", "running", "aab"),
          ("brain-ada-api-1", "brain-ada", "running", "bbb"), ("brain-ada-postgres-1", "brain-ada", "exited", "bbc"),
          ("brain-bob-api-1", "brain-bob", "exited", "ccc"))
STATS = "\n".join(json.dumps({"Name": n, "MemUsage": m}) for n, m in (
    ("brain-api-1", "1GiB / 8GiB"), ("brain-ollama-1", "3GiB / 8GiB"), ("brain-ada-api-1", "512MiB / 8GiB"), ("brain-ada-postgres-1", "0B / 8GiB")))
DF_V = json.dumps({"Volumes": [{"Name": "brain_postgres_data", "Size": "2GB"}, {"Name": "brain-ada_postgres_data", "Size": "500MB"},
                               {"Name": "brain-ada_api_data", "Size": "100MB"}, {"Name": "brain-bob_postgres_data", "Size": "9GB"}]})
HOST = {"disk": {"total_gb": 40.0, "used_gb": 38.0, "free_gb": 2.0, "pct": 95.0, "level": "alert"},
        "memory": {"total_gb": 8.6, "available_gb": 4.0, "available_pct": 46.5, "level": "ok"},
        "load": {"one": 9.0, "five": 9.0, "fifteen": 9.0, "cores": 2, "level": "alert"}, "uptime_days": 3.0}


@pytest.fixture
def box(monkeypatch):
    """Stub docker, the host and the brain's own files; returns a setter for the ps listing."""
    state = {"ps": BOX}

    def run(cmd, timeout=15):
        if cmd[:2] == ["docker", "ps"]:
            return state["ps"]
        if cmd[:2] == ["docker", "stats"]:
            return STATS
        if cmd[:3] == ["docker", "system", "df"]:
            return DF_V if "-v" in cmd else json.dumps({"Type": "Images", "TotalCount": 9, "Size": "9GB", "Reclaimable": "6GB"})
        return ""
    monkeypatch.setattr(s, "_run", run)
    monkeypatch.setattr(s, "host", lambda d: json.loads(json.dumps(HOST)))
    monkeypatch.setattr(s, "backups", lambda d: {"count": 1, "latest": "x", "age_days": 0.5, "size_gb": 0.1, "level": "ok", "dir": d})
    monkeypatch.setattr(s, "last_update", lambda d: {"running_commit": "abc1234"})
    monkeypatch.setattr(s, "database", lambda f: {"size_gb": 0.2, "documents": 3, "chunks": 30, "level": "ok"})
    monkeypatch.setattr(s, "_cgroup_mem", lambda: 300e6)
    monkeypatch.setattr(s, "_du", lambda paths: 50e6)
    monkeypatch.setattr(s.socket, "gethostname", lambda: "aaa000000000")
    for k in ("BRAIN_MEMBER", "COMPOSE_PROJECT_NAME"):
        monkeypatch.delenv(k, raising=False)
    return lambda ps: state.update(ps=ps)


def test_single_brain_report_unchanged(box):
    box(_ps(("brain-api-1", "brain", "running", "aaa"), ("brain-ui-1", "brain", "exited", "aac")))
    r = s.report("/x", None)
    assert set(r) == {"at", "host", "docker", "backups", "update", "database", "warnings", "level"}
    assert r["host"] == HOST and set(r["docker"]["containers"][0]) == {"name", "state", "status", "image"}
    assert r["docker"]["images"] == {"count": 9, "size": "9GB"} and r["docker"]["reclaimable_gb"] == 6.0
    assert r["warnings"] == ["disk 95.0% used, 2.0 GB free", "load 9.0 on 2 cores", "not running: brain-ui-1",
                             "docker holds 6.0 GB reclaimable"]
    assert r["level"] == "alert"


def test_first_brain_groups_and_keeps_the_admin_view(box):
    r = s.report("/x", None)
    assert r["shared"] == {"role": "first", "brains": 3} and "host" not in r
    assert r["box"]["brains"] == 3 and r["box"]["disk"]["free_gb"] == 2.0 and "level" not in r["box"]["load"]
    tb = r["this_brain"]
    assert tb["project"] == "brain" and (tb["containers"], tb["running"]) == (2, 2)
    assert tb["memory"]["used_gb"] == round(4 * 1024 ** 3 / 1e9, 2) and tb["memory"]["source"].startswith("its containers")
    assert tb["disk"]["used_gb"] == 2.0 and tb["disk"]["share_pct"] == 5.0 and tb["disk"]["level"] == "ok"
    names = [c["name"] for c in r["docker"]["containers"]]
    assert "brain-bob-api-1" in names and r["docker"]["images"]                      # the admin sees everything
    assert "shared box: disk 95.0% used, 2.0 GB free" in r["warnings"]
    assert not any(w.startswith("load") for w in r["warnings"])                         # box load: shown, never a warning
    assert "this brain holds 4.29 GB memory, 49.9% of the box" not in r["warnings"]    # under the 50% share


def test_member_sees_only_itself(box, monkeypatch):
    monkeypatch.setenv("BRAIN_MEMBER", "ada")
    monkeypatch.setenv("COMPOSE_PROJECT_NAME", "brain-ada")
    r = s.report("/x", None)
    assert r["shared"] == {"role": "member", "brains": 3}
    assert [c["name"] for c in r["docker"]["containers"]] == ["brain-ada-api-1", "brain-ada-postgres-1"]
    assert set(r["docker"]) == {"containers", "level", "not_running"}                  # nothing of the box's images
    assert r["this_brain"]["disk"]["used_gb"] == 0.6 and r["this_brain"]["memory"]["used_gb"] == round(512 * 1024 ** 2 / 1e9, 2)
    dump = json.dumps(r)
    assert "bob" not in dump and "brain-api-1" not in dump and "ollama" not in dump    # no other member, no first brain
    assert r["warnings"] == ["shared box: disk 95.0% used, 2.0 GB free", "not running: brain-ada-postgres-1"]


def test_member_without_docker_reports_its_narrower_source(box, monkeypatch):
    monkeypatch.setenv("BRAIN_MEMBER", "ada")
    monkeypatch.setenv("COMPOSE_PROJECT_NAME", "brain-ada")
    box("")
    r = s.report("/x", None)
    assert r["shared"] == {"role": "member", "brains": None} and r["docker"]["containers"] == []
    assert r["this_brain"]["memory"] == {"used_gb": 0.3, "source": "the api container only (cgroup)", "share_pct": 3.5, "level": "ok"}
    assert r["this_brain"]["disk"]["used_gb"] == 0.25 and r["this_brain"]["disk"]["source"].startswith("its database")


def test_shared_warnings_name_this_brain_and_the_box():
    rep = {"shared": {"role": "member"}, "box": {"disk": {"level": "ok"}, "memory": {"level": "alert", "available_gb": 0.4, "total_gb": 8.0}},
           "this_brain": {"memory": {"level": "warn", "used_gb": 4.5, "share_pct": 56.0}, "disk": {"level": "ok"}},
           "docker": {}, "backups": {"level": "ok", "count": 1}, "database": {}}
    assert s.warnings(rep) == ["shared box: memory 0.4 GB available of 8.0", "this brain holds 4.5 GB memory, 56.0% of the box"]
    assert s.overall(rep) == "alert"


def test_shared_role_counts_never_names():
    rows = s.ps_rows(BOX)
    assert s.shared_role("", "brain", rows) == {"role": "first", "brains": 3}
    assert s.shared_role("", "brain", [r for r in rows if r["project"] == "brain"]) is None
    assert s.shared_role("ada", "brain-ada", rows) == {"role": "member", "brains": 3}
    assert s._bytes("512MiB") == 512 * 1024 ** 2 and s._bytes("2GB") == 2e9 and s._bytes("0B") == 0
