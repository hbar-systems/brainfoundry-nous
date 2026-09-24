"""The technical surface (2026-09-24): what the box is doing, in numbers, with thresholds.

Read from inside the api container, which sees the host's memory and load through /proc,
the host's disk through the bind-mounted brain directory, and Docker through the socket the
Update tab already uses. Nothing here changes anything. The bridge on the host adds what a
container cannot see (the tailnet, connections, failed services) at GET /cc/system.

Asked for by the operator after finding the disk at 85% by accident: "some technical surface
in the brain so that I can keep track of the health of the box".
"""
from __future__ import annotations

import json
import os
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


def docker() -> Dict[str, Any]:
    d: Dict[str, Any] = {"containers": [], "images": None, "reclaimable_gb": None}
    out = _run(["docker", "ps", "-a", "--format", "{{json .}}"])
    for line in out.splitlines():
        try:
            c = json.loads(line)
        except ValueError:
            continue
        d["containers"].append({"name": c.get("Names"), "state": c.get("State"), "status": c.get("Status"), "image": c.get("Image")})
    down = [c for c in d["containers"] if c.get("state") != "running" and not (c.get("name") or "").startswith("brain-update")]
    d["level"] = "alert" if down else "ok"
    d["not_running"] = [c["name"] for c in down]
    df = _run(["docker", "system", "df", "--format", "{{json .}}"])
    total_reclaim = 0.0
    for line in df.splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if row.get("Type") == "Images":
            d["images"] = {"count": row.get("TotalCount"), "size": row.get("Size")}
        rec = str(row.get("Reclaimable") or "0B").split(" ")[0]
        total_reclaim += _to_gb(rec)
    d["reclaimable_gb"] = round(total_reclaim, 2)
    return d


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


def warnings(report: Dict[str, Any]) -> List[str]:
    """One short line per thing that crossed a threshold. Pure; tested."""
    w: List[str] = []
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


def report(brain_dir: str, conn_factory) -> Dict[str, Any]:
    r = {"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "host": host(brain_dir), "docker": docker(),
         "backups": backups(brain_dir), "update": last_update(brain_dir), "database": database(conn_factory)}
    r["warnings"] = warnings(r)
    levels = [x.get("level") for x in (r["host"].get("disk"), r["host"].get("memory"), r["host"].get("load"), r["docker"], r["backups"], r["database"]) if isinstance(x, dict)]
    r["level"] = "alert" if "alert" in levels else ("warn" if "warn" in levels else "ok")
    return r
