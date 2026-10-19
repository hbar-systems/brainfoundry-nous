"""The technical surface (2026-09-24): what the box is doing, in numbers, with thresholds.

Read from inside the api container, which sees the host's memory and load through /proc,
the host's disk through the bind-mounted brain directory, and Docker through the socket the
Update tab already uses. Nothing here changes anything. The bridge on the host adds what a
container cannot see (the tailnet, connections, failed services) at GET /cc/system.

Asked for by the operator after finding the disk at 85% by accident: "some technical surface
in the brain so that I can keep track of the health of the box".

A shared box (2026-10-19, docs/MULTI_INSTANCE.md): several members' brains on one machine. The
host's memory, load and disk are then the box's, and docker sees every member's containers. A
brain that knows it is shared (BRAIN_MEMBER set, or the first brain seeing member compose
projects) reports two groups instead of one: "this_brain" (its own compose project's containers,
RAM and volumes) and "box" (total memory, load, disk free, the number of brains, no names). A
member sees only its own containers; the first brain's admin view keeps the full list. One brain
alone: the report is exactly what it was.
"""
from __future__ import annotations

import json
import os
import re
import socket
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# Thresholds: warn at the first number, alert at the second.
DISK_PCT = (80, 90)
MEM_AVAILABLE_PCT = (15, 7)       # available memory as a share of total: warn below 15, alert below 7
LOAD_PER_CORE = (1.0, 2.0)
BACKUP_AGE_DAYS = (2, 7)
BRAIN_SHARE_PCT = (50, 75)        # shared box: this brain's RAM or disk as a share of the box's total

# A member's compose project (scripts/add-member.sh, cc_member.handle_ok): brain-<flat handle>.
MEMBER_PROJECT = re.compile(r"^brain-[a-z][a-z0-9]{1,15}$")
PROJECT_LABEL = "com.docker.compose.project"
# The api's own files when docker is out of reach (a member's api has no socket by default).
APP_DIRS = ("/app/data", "/app/runtime", "/app/extensions/brain", "/app/brain-apps", "/app/prepared_docs")


def level(value: float, warn: float, alert: float, lower_is_worse: bool = False) -> str:
    """'ok', 'warn' or 'alert' for one number against its two thresholds. Pure; tested."""
    if lower_is_worse:
        if value < alert:
            return "alert"
        return "warn" if value < warn else "ok"
    if value >= alert:
        return "alert"
    return "warn" if value >= warn else "ok"


def _meminfo() -> Dict[str, int]:
    out: Dict[str, int] = {}
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            k, _, v = line.partition(":")
            out[k.strip()] = int(v.strip().split()[0]) * 1024
    except Exception:
        pass
    return out


def host(brain_dir: str) -> Dict[str, Any]:
    d: Dict[str, Any] = {}
    try:
        u = shutil.disk_usage(brain_dir if os.path.isdir(brain_dir) else "/")
        pct = round(100 * u.used / u.total, 1) if u.total else 0.0
        d["disk"] = {"total_gb": round(u.total / 1e9, 1), "used_gb": round(u.used / 1e9, 1), "free_gb": round(u.free / 1e9, 1),
                     "pct": pct, "level": level(pct, *DISK_PCT)}
    except Exception as e:
        d["disk"] = {"error": str(e)}
    m = _meminfo()
    if m.get("MemTotal"):
        avail = m.get("MemAvailable", 0)
        pct_avail = round(100 * avail / m["MemTotal"], 1)
        d["memory"] = {"total_gb": round(m["MemTotal"] / 1e9, 1), "available_gb": round(avail / 1e9, 1),
                       "available_pct": pct_avail, "level": level(pct_avail, *MEM_AVAILABLE_PCT, lower_is_worse=True)}
    try:
        l1, l5, l15 = os.getloadavg()
        cores = os.cpu_count() or 1
        d["load"] = {"one": round(l1, 2), "five": round(l5, 2), "fifteen": round(l15, 2), "cores": cores,
                     "level": level(l5 / cores, *LOAD_PER_CORE)}
    except Exception:
        pass
    try:
        up = float(Path("/proc/uptime").read_text().split()[0])
        d["uptime_days"] = round(up / 86400, 1)
    except Exception:
        pass
    return d


def _run(cmd: List[str], timeout: int = 15) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout if r.returncode == 0 else ""
    except Exception:
        return ""


def _labels(s: str) -> Dict[str, str]:
    """`docker ps --format {{json .}}` Labels, "a=b,c=d", as a dict. Pure."""
    out: Dict[str, str] = {}
    for part in (s or "").split(","):
        k, eq, v = part.partition("=")
        if eq:
            out[k.strip()] = v.strip()
    return out


def ps_rows(out: str) -> List[Dict[str, Any]]:
    """Every container docker lists, with its compose project and short id. Pure; tested."""
    rows = []
    for line in out.splitlines():
        try:
            c = json.loads(line)
        except ValueError:
            continue
        rows.append({"name": c.get("Names"), "state": c.get("State"), "status": c.get("Status"), "image": c.get("Image"),
                     "id": (c.get("ID") or "")[:12], "project": _labels(c.get("Labels") or "").get(PROJECT_LABEL, "")})
    return rows


def docker(rows: Optional[List[Dict[str, Any]]] = None, full: bool = True) -> Dict[str, Any]:
    """Containers and images. `rows` from ps_rows (read here when None); `full` False is a member's
    view on a shared box: its own containers only, nothing about the box's images."""
    d: Dict[str, Any] = {"containers": [], "images": None, "reclaimable_gb": None}
    if rows is None:
        rows = ps_rows(_run(["docker", "ps", "-a", "--format", "{{json .}}"]))
    for c in rows:
        d["containers"].append({"name": c.get("name"), "state": c.get("state"), "status": c.get("status"), "image": c.get("image")})
    down = [c for c in d["containers"] if c.get("state") != "running" and not (c.get("name") or "").startswith("brain-update")]
    d["level"] = "alert" if down else "ok"
    d["not_running"] = [c["name"] for c in down]
    if not full:
        return {"containers": d["containers"], "level": d["level"], "not_running": d["not_running"]}
    df = _run(["docker", "system", "df", "--format", "{{json .}}"])
    total_reclaim = 0.0
    by_type: Dict[str, float] = {}
    for line in df.splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if row.get("Type") == "Images":
            d["images"] = {"count": row.get("TotalCount"), "size": row.get("Size")}
        rec = str(row.get("Reclaimable") or "0B").split(" ")[0]
        gb = _to_gb(rec)
        by_type[str(row.get("Type") or "?")] = round(gb, 2)
        total_reclaim += gb
    d["reclaimable_gb"] = round(total_reclaim, 2)
    d["reclaimable_by_type"] = by_type
    # "Reclaimable" above is everything no running container uses: tagged images, stopped
    # containers, volumes, build cache. "reclaim now" and the update only remove dangling
    # (untagged) images, so that is the number the button must show (hbar, 2026-10-11: the
    # tile said 1.79 GB, the button reclaimed 0B).
    d["dangling_gb"] = dangling_gb(_run(["docker", "images", "-f", "dangling=true", "--format", "{{.Size}}"]))
    return d


def dangling_gb(sizes: str) -> float:
    """Sum of `docker images -f dangling=true --format {{.Size}}` lines, in GB."""
    return round(sum(_to_gb(x) for x in sizes.splitlines() if x.strip()), 2)


def _to_gb(s: str) -> float:
    s = s.strip().upper()
    try:
        for suf, mult in (("TB", 1000), ("GB", 1), ("MB", 0.001), ("KB", 1e-6), ("B", 1e-9)):
            if s.endswith(suf):
                return float(s[: -len(suf)]) * mult
    except ValueError:
        pass
    return 0.0


def backups(brain_dir: str) -> Dict[str, Any]:
    p = Path(brain_dir) / ".brain-backups"
    files = sorted(p.glob("*"), key=lambda x: x.stat().st_mtime) if p.is_dir() else []
    if not files:
        return {"count": 0, "latest": None, "age_days": None, "level": "warn", "dir": str(p)}
    latest = files[-1]
    age = (time.time() - latest.stat().st_mtime) / 86400
    size = sum(f.stat().st_size for f in files if f.is_file())
    return {"count": len(files), "latest": latest.name, "age_days": round(age, 1), "size_gb": round(size / 1e9, 2),
            "level": level(age, *BACKUP_AGE_DAYS), "dir": str(p)}


def last_update(brain_dir: str) -> Dict[str, Any]:
    d: Dict[str, Any] = {}
    log = Path(brain_dir) / ".update-helper.log"
    if log.exists():
        d["helper_log_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(log.stat().st_mtime))
    prev = Path(brain_dir) / ".update-prev-commit"
    if prev.exists():
        d["previous_commit"] = prev.read_text().strip()[:7]
    d["running_commit"] = (os.getenv("BRAIN_GIT_COMMIT") or "unknown")[:7]
    d["built_at"] = os.getenv("BRAIN_BUILD_TIME") or None
    return d


def database(conn_factory) -> Dict[str, Any]:
    try:
        conn = conn_factory()
        cur = conn.cursor()
        cur.execute("SELECT pg_database_size(current_database())")
        size = cur.fetchone()[0]
        cur.execute("SELECT count(DISTINCT document_name) FROM document_embeddings")
        docs = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM document_embeddings")
        chunks = cur.fetchone()[0]
        conn.close()
        return {"size_gb": round(size / 1e9, 3), "documents": docs, "chunks": chunks, "level": "ok"}
    except Exception as e:
        return {"error": f"{type(e).__name__}", "level": "warn"}


def _bytes(s: str) -> float:
    """"45.1MiB" or "1.2GB" in bytes; binary and decimal suffixes both. Pure."""
    m = re.match(r"^\s*([0-9.]+)\s*([KMGT]?i?B)\s*$", s or "", re.I)
    if not m:
        return 0.0
    n, suf = float(m.group(1)), m.group(2).upper()
    base = 1024 if "I" in suf else 1000
    return n * base ** "BKMGT".index(suf[0]) if suf[0] in "KMGT" else n


def stats_mem_bytes(out: str, names) -> float:
    """Sum of MemUsage over `docker stats --no-stream --format {{json .}}` lines for `names`. Pure."""
    want, total = set(names), 0.0
    for line in out.splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if row.get("Name") in want:
            total += _bytes(str(row.get("MemUsage") or "").split("/")[0])
    return total


def volumes_bytes(out: str, project: str) -> float:
    """Sum of the sizes of `project`'s volumes in `docker system df -v --format {{json .}}`. Pure."""
    total = 0.0
    for line in out.splitlines():
        try:
            j = json.loads(line)
        except ValueError:
            continue
        for v in j.get("Volumes") or []:
            if str(v.get("Name") or "").startswith(project + "_"):
                total += _bytes(str(v.get("Size") or "0B"))
    return total


def _cgroup_mem() -> float:
    for f in ("/sys/fs/cgroup/memory.current", "/sys/fs/cgroup/memory/memory.usage_in_bytes"):
        try:
            return float(Path(f).read_text().strip())
        except Exception:
            continue
    return 0.0


def _du(paths) -> float:
    total = 0
    for p in paths:
        for root, _dirs, files in os.walk(p):
            for f in files:
                try:
                    total += os.lstat(os.path.join(root, f)).st_size
                except OSError:
                    pass
    return float(total)


def shared_role(member: str, own_project: str, rows: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """None for a brain alone on its box; else {"role": "member"|"first", "brains": n or None}.
    A member knows from BRAIN_MEMBER; the first brain from other member projects docker shows it.
    Counts only, never names. Pure; tested."""
    others = {r["project"] for r in rows if MEMBER_PROJECT.match(r.get("project") or "") and r.get("project") != own_project}
    if member:
        # A member's api sees docker only with --update-tab; then it can count, never name: the
        # other members, itself, and the first brain (always there: add-member.sh joins a running one).
        return {"role": "member", "brains": (len(others) + 2) if rows else None}
    if others:
        return {"role": "first", "brains": len(others) + 1}
    return None


def this_brain(project: str, rows: List[Dict[str, Any]], box: Dict[str, Any], mem_bytes: Optional[float],
               disk_bytes: Optional[float], fallback_mem: float, fallback_disk: float) -> Dict[str, Any]:
    """This brain's own usage on a shared box, with its share of the box and a level. Pure; tested.
    mem_bytes / disk_bytes None: docker was out of reach; the fallbacks (the api container's cgroup,
    the database plus the api's files) are reported with their narrower source."""
    own = [r for r in rows if project and r.get("project") == project]
    d: Dict[str, Any] = {"project": project or None, "containers": len(own),
                         "running": sum(1 for r in own if r.get("state") == "running")}

    def part(used: float, source: str, total_gb: Optional[float]) -> Dict[str, Any]:
        gb = round(used / 1e9, 2)
        out: Dict[str, Any] = {"used_gb": gb, "source": source}
        if total_gb:
            share = round(100 * gb / total_gb, 1)
            out["share_pct"] = share
            out["level"] = level(share, *BRAIN_SHARE_PCT)
        return out
    mem_total = (box.get("memory") or {}).get("total_gb")
    disk_total = (box.get("disk") or {}).get("total_gb")
    d["memory"] = part(mem_bytes, "its containers (docker stats)", mem_total) if mem_bytes is not None \
        else part(fallback_mem, "the api container only (cgroup)", mem_total)
    d["disk"] = part(disk_bytes, "its volumes (docker system df)", disk_total) if disk_bytes is not None \
        else part(fallback_disk, "its database and the api's files", disk_total)
    return d


def warnings(report: Dict[str, Any]) -> List[str]:
    """One short line per thing that crossed a threshold. Pure; tested.
    On a shared box: this brain's own usage, and the box's totals only when the box is short
    (disk, memory available); load and docker's reclaimable space only for the first brain's admin."""
    w: List[str] = []
    sh = report.get("shared")
    if sh:
        bx = report.get("box") or {}
        if (bx.get("disk") or {}).get("level") in ("warn", "alert"):
            w.append(f"shared box: disk {bx['disk']['pct']}% used, {bx['disk']['free_gb']} GB free")
        if (bx.get("memory") or {}).get("level") in ("warn", "alert"):
            w.append(f"shared box: memory {bx['memory']['available_gb']} GB available of {bx['memory']['total_gb']}")
        tb = report.get("this_brain") or {}
        for k, what in (("memory", "memory"), ("disk", "disk")):
            x = tb.get(k) or {}
            if x.get("level") in ("warn", "alert"):
                w.append(f"this brain holds {x['used_gb']} GB {what}, {x['share_pct']}% of the box")
    else:
        h = report.get("host") or {}
        if (h.get("disk") or {}).get("level") in ("warn", "alert"):
            w.append(f"disk {h['disk']['pct']}% used, {h['disk']['free_gb']} GB free")
        if (h.get("memory") or {}).get("level") in ("warn", "alert"):
            w.append(f"memory {h['memory']['available_gb']} GB available of {h['memory']['total_gb']}")
        if (h.get("load") or {}).get("level") in ("warn", "alert"):
            w.append(f"load {h['load']['five']} on {h['load']['cores']} cores")
    dk = report.get("docker") or {}
    if dk.get("not_running"):
        w.append("not running: " + ", ".join(dk["not_running"]))
    if (dk.get("reclaimable_gb") or 0) >= 5:
        w.append(f"docker holds {dk['reclaimable_gb']} GB reclaimable")
    b = report.get("backups") or {}
    if b.get("level") in ("warn", "alert"):
        w.append("no backup yet" if not b.get("count") else f"last backup {b['age_days']} days ago")
    if (report.get("database") or {}).get("level") == "warn":
        w.append("database not answering the size query")
    return w


def shape_shared(r: Dict[str, Any], sh: Dict[str, Any], tb: Dict[str, Any], rows: List[Dict[str, Any]], project: str) -> Dict[str, Any]:
    """Turn a single-brain report `r` into the two groups. A member's docker view keeps only its own
    project's containers; the first brain keeps the full list (the admin view). Pure; tested."""
    host = r.pop("host", {}) or {}
    box = {k: host[k] for k in ("disk", "memory", "uptime_days") if k in host}
    if "load" in host:
        box["load"] = {k: v for k, v in host["load"].items() if k != "level"}   # shown, never a warning here
    box["brains"] = sh.get("brains")
    r["shared"] = sh
    r["box"] = box
    r["this_brain"] = tb
    if sh["role"] == "member":
        r["docker"] = docker([x for x in rows if project and x.get("project") == project], full=False)
    return r


def overall(r: Dict[str, Any]) -> str:
    if r.get("shared"):
        bx, tb = r.get("box") or {}, r.get("this_brain") or {}
        parts = (bx.get("disk"), bx.get("memory"), tb.get("memory"), tb.get("disk"), r.get("docker"), r.get("backups"), r.get("database"))
    else:
        h = r.get("host") or {}
        parts = (h.get("disk"), h.get("memory"), h.get("load"), r.get("docker"), r.get("backups"), r.get("database"))
    levels = [x.get("level") for x in parts if isinstance(x, dict)]
    return "alert" if "alert" in levels else ("warn" if "warn" in levels else "ok")


def report(brain_dir: str, conn_factory) -> Dict[str, Any]:
    rows = ps_rows(_run(["docker", "ps", "-a", "--format", "{{json .}}"]))
    member = (os.getenv("BRAIN_MEMBER") or "").strip()
    project = (os.getenv("COMPOSE_PROJECT_NAME") or "").strip()
    if not project:
        me = socket.gethostname()[:12]
        project = next((x["project"] for x in rows if x.get("id") and x["id"] == me), "")
    sh = shared_role(member, project, rows)
    r = {"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "host": host(brain_dir), "docker": docker(rows),
         "backups": backups(brain_dir), "update": last_update(brain_dir), "database": database(conn_factory)}
    if sh:
        own = [x["name"] for x in rows if project and x.get("project") == project]
        mem = disk = None
        if own:
            mem = stats_mem_bytes(_run(["docker", "stats", "--no-stream", "--format", "{{json .}}", *own], timeout=30), own)
            disk = volumes_bytes(_run(["docker", "system", "df", "-v", "--format", "{{json .}}"], timeout=60), project)
        db_bytes = (r["database"].get("size_gb") or 0) * 1e9
        tb = this_brain(project, rows, r["host"], mem, disk,
                        _cgroup_mem() if mem is None else 0.0, (db_bytes + _du(APP_DIRS)) if disk is None else 0.0)
        r = shape_shared(r, sh, tb, rows, project)
    r["warnings"] = warnings(r)
    r["level"] = overall(r)
    return r
