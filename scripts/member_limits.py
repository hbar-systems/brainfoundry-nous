#!/usr/bin/env python3
"""member_limits.py — per-member limits on a shared box: what one member may take of CPU, memory,
processes, disk, jobs and spend, so one member (or its reasoner, or its jobs) cannot starve the rest.

Created 2026-11-06 (SEC-1, front 3; docs/MEMBER_LIMITS.md). Standard library, plus PyYAML for
`merge` and `check` (Ubuntu's cloud-init ships it). Every subcommand only prints; none writes a file,
starts a container or touches a unit. scripts/add-member.sh writes what it prints.

    python3 scripts/member_limits.py profile                       # the per-member limits in force (env overrides)
    python3 scripts/member_limits.py override [--update-tab DIR]   # a new member's docker-compose.override.yml
    python3 scripts/member_limits.py merge <override> [--admin]    # an existing override with the limits merged in
    python3 scripts/member_limits.py unit <m|admin> slice|bridge|term|env   # one systemd file (or the limits env)
    python3 scripts/member_limits.py parent brain|system [TSV]     # the parents' MemoryLow (reservations need it)
    python3 scripts/member_limits.py check [--plan] [--members TSV] # per-member limits and the box total vs capacity
    sudo python3 scripts/member_limits.py disk [--members TSV]      # each member's disk use against its quota

Two layers. Containers: cpus, mem_limit (ceiling, OOM kill), mem_reservation (memory.low under
cgroup v2: kept for this member when the box is short), pids_limit, per service, in the member's
docker-compose.override.yml. Host: the member's bridge and terminal units (so its reasoner and every
cc-job, which run as <m>-hands under sudo inside those units) go into brain-<m>.slice with CPUQuota,
MemoryHigh, MemoryMax, MemoryLow and TasksMax; the bridge also reads /etc/brainfoundry/limits-<m>.env
(root's file, read after the bridge's own env file, so it wins): CC_MAX_JOBS and CC_SPEND_CAP_EUR.
Disk on ext4 cannot be capped per docker volume, so `disk` measures and alarms (docs/MEMBER_LIMITS.md).

The check fails (exit 1) when any tenant is unlimited, when the guaranteed memory (reservations, plus
the host's own reserve) is more than the box has, when one tenant's ceiling is more than its allowed
share of the box, when the sum of ceilings passes the overcommit bound, or when the disk quotas
plus the shared reserve are more than the disk. Box numbers default to friends-1 (CAX31).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------- the profile ----
# Sized for friends-1 (CAX31: 8 vCPU, 15577 MiB, 150 GB) with five members plus the admin brain and
# the one shared Ollama. Reservations: 6 x 1536 + 3072 (Ollama) + 1024 (host) = 13312 MiB of 15577.
SERVICES = ("api", "ui", "nodeos", "public-chat", "postgres", "redis")
DEFAULT_SERVICES = {        # cpus, ceiling, reservation, pids
    "api":         ("1.5",  "2560m", "768m", 512),   # in-process bge-large on first embed: about 1.8 GB
    "ui":          ("0.5",  "384m",  "128m", 128),
    "nodeos":      ("0.25", "256m",  "64m",  128),
    "public-chat": ("0.5",  "256m",  "96m",  128),
    "postgres":    ("1.0",  "768m",  "192m", 256),
    "redis":       ("0.25", "128m",  "32m",  64),
}
DEFAULT_OLLAMA = ("6.0", "5120m", "3072m", 256)       # the admin brain's Ollama, shared by every member
DEFAULT_OLLAMA_ENV = {"OLLAMA_NUM_PARALLEL": "2", "OLLAMA_MAX_LOADED_MODELS": "2"}
DEFAULT_SLICE = {"cpus": "1.5", "mem_high": "2048m", "mem": "2560m", "mem_res": "256m", "tasks": 1024}
DEFAULT_JOBS = 3            # cc-jobs running at once
DEFAULT_SPEND_EUR = 0       # admin ceiling on the ledger, EUR per 30 days; 0 = none (the provider key's cap rules)
DEFAULT_DISK_GB = 15        # one member's checkout, homes and volumes

BOX = {"mem_mb": 15577, "cpus": 8, "disk_gb": 150, "host_reserve_mb": 1024, "disk_reserve_gb": 40,
       "max_share": 0.5, "max_cpu_share": 0.75, "max_overcommit": 4.0, "min_free_pct": 10}

LIMITS_DIR = "/etc/brainfoundry"


def env_key(svc: str, field: str) -> str:
    return f"BRAIN_LIMIT_{svc.upper().replace('-', '_')}_{field}"


def mib(v) -> int | None:
    """'2560m', '2g', '2560M', '512k', 2560 (MiB) -> MiB. None, '', 0, 'infinity' -> None (no limit)."""
    if v is None:
        return None
    if isinstance(v, bool):
        raise ValueError(f"not a size: {v!r}")
    if isinstance(v, (int, float)):      # a bare number is bytes, as compose and docker read it
        return None if v <= 0 else max(1, int(round(v / 1048576)))
    s = str(v).strip().lower()
    if s in ("", "0", "infinity", "-1", "max"):
        return None
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*([kmgt]?)i?b?", s)
    if not m:
        raise ValueError(f"not a size: {v!r}")
    n, u = float(m.group(1)), m.group(2)
    if u == "":                          # bare number: bytes, as docker reads it
        return None if n <= 0 else max(1, int(round(n / 1048576)))
    return int(round(n * {"k": 1 / 1024, "m": 1, "g": 1024, "t": 1024 * 1024}[u]))


def num(v) -> float | None:
    if v in (None, ""):
        return None
    f = float(v)
    return None if f <= 0 else f


def _svc(env, svc, d):
    g = lambda f, dv: env.get(env_key(svc, f)) or dv  # noqa: E731
    return {"cpus": g("CPUS", d[0]), "mem": g("MEM", d[1]), "mem_res": g("MEM_RES", d[2]), "pids": int(g("PIDS", d[3]))}


def profile(env=None) -> dict:
    """One member's limits: the defaults above, each overridable by BRAIN_LIMIT_<SERVICE>_<FIELD>."""
    env = os.environ if env is None else env
    p = {"services": {s: _svc(env, s, DEFAULT_SERVICES[s]) for s in SERVICES},
         "ollama": _svc(env, "ollama", DEFAULT_OLLAMA),
         "slice": {k: env.get(f"BRAIN_LIMIT_SLICE_{k.upper()}") or v for k, v in DEFAULT_SLICE.items()},
         "jobs": int(env.get("BRAIN_LIMIT_JOBS") or DEFAULT_JOBS),
         "spend_eur": float(env.get("BRAIN_LIMIT_SPEND_EUR") or DEFAULT_SPEND_EUR),
         "disk_gb": float(env.get("BRAIN_LIMIT_DISK_GB") or DEFAULT_DISK_GB)}
    p["slice"]["tasks"] = int(p["slice"]["tasks"])
    for where in [*p["services"].values(), p["ollama"]]:
        mib(where["mem"]), mib(where["mem_res"]), num(where["cpus"])   # refuse a bad value early
        if mib(where["mem_res"]) and mib(where["mem"]) and mib(where["mem_res"]) > mib(where["mem"]):
            raise ValueError("a reservation is larger than its ceiling")
    return p


def box(env=None) -> dict:
    env = os.environ if env is None else env
    return {k: type(v)(env.get(f"BOX_{k.upper()}") or v) for k, v in BOX.items()}


# ---------------------------------------------------------------- compose ----
def _limit_lines(lim: dict, indent: str = "    ") -> list[str]:
    return [f"{indent}cpus: {lim['cpus']}", f"{indent}mem_limit: {mib(lim['mem'])}m",
            f"{indent}mem_reservation: {mib(lim['mem_res'])}m", f"{indent}pids_limit: {int(lim['pids'])}"]


def member_override(p: dict, update_tab_dir: str | None = None) -> str:
    """A new member's docker-compose.override.yml: the shared Ollama, the limits, the Update tab if asked."""
    out = ["# Written by scripts/add-member.sh: the shared Ollama (docs/MULTI_INSTANCE.md) and this member's",
           "# limits (docs/MEMBER_LIMITS.md, scripts/member_limits.py).",
           "services:",
           "  ollama:",
           '    profiles: ["own-ollama"]   # the box\'s one Ollama answers as "ollama" (docs/MULTI_INSTANCE.md)']
    for s in SERVICES:
        out += [f"  {s}:"] + _limit_lines(p["services"][s])
        if s == "api" and update_tab_dir:
            out += ["    volumes:", "      - /var/run/docker.sock:/var/run/docker.sock",
                    f"      - {update_tab_dir}:{update_tab_dir}:rw"]
    return "\n".join(out) + "\n"


def _yaml():
    try:
        import yaml
        return yaml
    except ImportError:
        sys.exit("refused: PyYAML is needed here (apt install python3-yaml)")


def merge_override(text: str, p: dict, admin: bool = False) -> str:
    """An existing override with the limits merged in: every other key (volumes, profiles,
    environment) is kept; a limit key already there is replaced. Comments are not kept (the caller
    backs the file up first). admin: the box's first brain, which runs the shared Ollama."""
    yaml = _yaml()
    doc = yaml.safe_load(text) if text.strip() else {}
    doc = doc or {}
    if not isinstance(doc, dict):
        raise ValueError("the override is not a mapping")
    svcs = doc.setdefault("services", {}) or {}
    doc["services"] = svcs

    def put(name, lim):
        s = svcs.get(name) or {}
        s.update({"cpus": float(lim["cpus"]), "mem_limit": f"{mib(lim['mem'])}m",
                  "mem_reservation": f"{mib(lim['mem_res'])}m", "pids_limit": int(lim["pids"])})
        svcs[name] = s
        return s

    for s in SERVICES:
        put(s, p["services"][s])
    if admin:
        o = put("ollama", p["ollama"])
        env = o.get("environment")
        if isinstance(env, list):
            keys = {str(e).split("=", 1)[0] for e in env}
            env += [f"{k}={v}" for k, v in DEFAULT_OLLAMA_ENV.items() if k not in keys]
        else:
            env = dict(env or {})
            for k, v in DEFAULT_OLLAMA_ENV.items():
                env.setdefault(k, v)
        o["environment"] = env
    head = "# Limits merged by scripts/member_limits.py merge (docs/MEMBER_LIMITS.md); the earlier file is beside it as .bak.\n"
    return head + yaml.safe_dump(doc, sort_keys=False, default_flow_style=False)


def read_override(path: Path) -> dict:
    """{service: {cpus, mem, mem_res, pids}} from an override file; a missing key is None (no limit)."""
    out = {}
    try:
        doc = _yaml().safe_load(path.read_text()) or {}
    except (OSError, ValueError):
        doc = {}
    svcs = (doc.get("services") if isinstance(doc, dict) else None) or {}
    for name in (*SERVICES, "ollama"):
        s = svcs.get(name) or {}
        out[name] = {"cpus": s.get("cpus"), "mem": s.get("mem_limit"), "mem_res": s.get("mem_reservation"),
                     "pids": s.get("pids_limit"), "profiles": s.get("profiles")}
    return out


# ---------------------------------------------------------------- systemd ----
def unit_names(m: str) -> tuple[str, str, str]:
    """slice, bridge unit, terminal unit. 'admin' is the box's first brain (units without a suffix)."""
    sfx = "" if m == "admin" else f"-{m}"
    return f"brain-{m}.slice", f"cc-bridge{sfx}.service", f"claude-tab{sfx}.service"


def unit_text(m: str, kind: str, p: dict, limits_dir: str = LIMITS_DIR) -> str:
    sl, bridge, term = unit_names(m)
    s = p["slice"]
    if kind == "slice":
        return (f"# Written by scripts/add-member.sh (docs/MEMBER_LIMITS.md): {m}'s bridge, terminal, reasoner and jobs.\n"
                f"[Unit]\nDescription=Brain {m}: reasoner and jobs, limited\n\n[Slice]\n"
                f"CPUQuota={int(round(float(s['cpus']) * 100))}%\nMemoryHigh={mib(s['mem_high'])}M\n"
                f"MemoryMax={mib(s['mem'])}M\nMemoryLow={mib(s['mem_res'])}M\nTasksMax={int(s['tasks'])}\n")
    if kind == "bridge":
        return (f"# {bridge}.d/limits.conf (docs/MEMBER_LIMITS.md). The second EnvironmentFile is root's and read\n"
                f"# after the bridge's own, so its CC_MAX_JOBS and CC_SPEND_CAP_EUR win.\n"
                f"[Service]\nSlice={sl}\nEnvironmentFile=-{limits_dir}/limits-{m}.env\n")
    if kind == "term":
        return f"# {term}.d/limits.conf (docs/MEMBER_LIMITS.md)\n[Service]\nSlice={sl}\n"
    if kind == "env":
        spend = p["spend_eur"]
        return (f"# {m}: limits the bridge enforces (docs/MEMBER_LIMITS.md). Root's file; not a secret.\n"
                f"CC_MAX_JOBS={p['jobs']}\n" + (f"CC_SPEND_CAP_EUR={spend:g}\n" if spend > 0 else "# CC_SPEND_CAP_EUR= (none: the provider key's own cap rules)\n"))
    raise ValueError(f"unknown unit kind {kind!r}")


def parent_text(kind: str, tenants: int, p: dict) -> str:
    """The parents' share of the reservations. cgroup v2 honours a child's memory.low only up to what its
    ancestors carry, so brain.slice (parent of every brain-<m>.slice) and system.slice (parent of every
    docker container's scope) hold the sum of their children's reservations; without these two the
    reservations protect nothing. tenants: the members plus the admin brain."""
    if kind == "brain":
        low = tenants * (mib(p["slice"]["mem_res"]) or 0)
        return (f"# /etc/systemd/system/brain.slice (docs/MEMBER_LIMITS.md): {tenants} tenants' reasoner slices.\n"
                f"[Unit]\nDescription=Every brain's reasoner and jobs\n\n[Slice]\nMemoryLow={low}M\n")
    if kind == "system":
        low = tenants * sum(mib(p["services"][s]["mem_res"]) or 0 for s in SERVICES) + (mib(p["ollama"]["mem_res"]) or 0)
        return (f"# /etc/systemd/system/system.slice.d/50-brain-limits.conf (docs/MEMBER_LIMITS.md): {tenants} tenants'\n"
                f"# container reservations and the shared Ollama's; docker's scopes live under system.slice.\n"
                f"[Slice]\nMemoryLow={low}M\n")
    raise ValueError(f"unknown parent {kind!r}")


def read_slice(path: Path) -> dict:
    out = {"cpus": None, "mem_high": None, "mem": None, "mem_res": None, "tasks": None}
    try:
        text = path.read_text()
    except OSError:
        return out
    kv = dict(re.findall(r"^(\w+)=(.*)$", text, re.M))
    if kv.get("CPUQuota", "").endswith("%"):
        out["cpus"] = float(kv["CPUQuota"][:-1]) / 100
    out["mem_high"], out["mem"], out["mem_res"] = kv.get("MemoryHigh"), kv.get("MemoryMax"), kv.get("MemoryLow")
    t = kv.get("TasksMax", "")
    out["tasks"] = int(t) if t.isdigit() else None
    return out


def read_limits_env(path: Path) -> dict:
    try:
        kv = dict(re.findall(r"^([A-Z_]+)=(.*)$", path.read_text(), re.M))
    except OSError:
        return {"jobs": None, "spend_eur": None}
    j = kv.get("CC_MAX_JOBS", "")
    return {"jobs": int(j) if j.isdigit() and int(j) > 0 else None,
            "spend_eur": num(kv.get("CC_SPEND_CAP_EUR")), "file": True}


# ---------------------------------------------------------------- the check ----
def members(tsv: Path) -> list[str]:
    try:
        lines = tsv.read_text().splitlines()
    except OSError:
        return []
    return [ln.split("\t")[0].split()[0] for ln in lines if ln.strip() and not ln.lstrip().startswith("#")]


def tenant_from_profile(p: dict) -> dict:
    return {"services": {s: dict(p["services"][s]) for s in SERVICES}, "slice": dict(p["slice"]),
            "jobs": p["jobs"], "spend_eur": p["spend_eur"] or None, "disk_gb": p["disk_gb"]}


def tenant_from_box(m: str, override: Path, systemd_dir: Path, limits_dir: Path, p: dict) -> dict:
    ov = read_override(override)
    le = read_limits_env(limits_dir / f"limits-{m}.env")
    return {"services": {s: ov[s] for s in SERVICES}, "slice": read_slice(systemd_dir / unit_names(m)[0]),
            "jobs": le["jobs"], "spend_eur": le["spend_eur"], "disk_gb": p["disk_gb"], "ollama": ov["ollama"]}


def sums(t: dict) -> dict:
    """One tenant's totals; None in a field means unlimited somewhere."""
    def add(vals):
        return None if any(v is None for v in vals) else sum(vals)
    svc = t["services"].values()
    sl = t["slice"]
    return {"mem": add([mib(s["mem"]) for s in svc] + [mib(sl["mem"])]),
            "mem_res": sum(mib(s["mem_res"]) or 0 for s in svc) + (mib(sl["mem_res"]) or 0),
            "cpus": add([num(s["cpus"]) for s in svc] + [num(sl["cpus"])]),
            "pids": add([(int(s["pids"]) if s["pids"] not in (None, "") and int(s["pids"]) > 0 else None) for s in svc]
                        + [sl["tasks"]]),
            "jobs": t["jobs"], "spend_eur": t["spend_eur"], "disk_gb": t["disk_gb"]}


def check(tenants: dict, ollama: dict | None, bx: dict) -> tuple[list[str], list[str]]:
    """(table lines, problems). tenants: {name: tenant}; ollama: the shared Ollama's limits or None."""
    fmt = lambda v, u="": "unlimited" if v is None else f"{v:g}{u}"  # noqa: E731
    lines = [f"{'tenant':<12}{'mem max':>11}{'mem res':>11}{'cpus':>11}{'pids':>11}{'jobs':>11}{'spend':>8}{'disk':>7}"]
    problems = []
    tot = {"mem": 0, "mem_res": 0, "cpus": 0.0, "disk": 0.0}
    unlimited = False
    for name, t in tenants.items():
        s = sums(t)
        spend = "none" if s["spend_eur"] is None else f"{s['spend_eur']:g}E"
        lines.append(f"{name:<12}{fmt(s['mem'], 'M'):>11}{fmt(s['mem_res'], 'M'):>11}{fmt(s['cpus']):>11}"
                     f"{fmt(s['pids']):>11}{fmt(s['jobs']):>11}{spend:>8}{fmt(s['disk_gb'], 'G'):>7}")
        for k, what in (("mem", "memory ceiling"), ("cpus", "cpu limit"), ("pids", "process limit")):
            if s[k] is None:
                problems.append(f"{name}: unlimited: no {what} on some service or on its slice")
                unlimited = True
        if s["jobs"] is None:
            problems.append(f"{name}: unlimited: no cap on running jobs (CC_MAX_JOBS)")
            unlimited = True
        if s["mem"] is not None:
            tot["mem"] += s["mem"]
            if s["mem"] > bx["max_share"] * bx["mem_mb"]:
                problems.append(f"{name}: memory ceiling {s['mem']}M is more than {bx['max_share']:.0%} of the box")
        if s["cpus"] is not None:
            tot["cpus"] += s["cpus"]
            if s["cpus"] > bx["max_cpu_share"] * bx["cpus"]:
                problems.append(f"{name}: {s['cpus']:g} cpus is more than {bx['max_cpu_share']:.0%} of {bx['cpus']}")
        tot["mem_res"] += s["mem_res"]
        tot["disk"] += s["disk_gb"] or 0
    if ollama is not None:
        om, orr = mib(ollama.get("mem")), mib(ollama.get("mem_res")) or 0
        lines.append(f"{'ollama':<12}{fmt(om, 'M'):>11}{fmt(orr, 'M'):>11}{fmt(num(ollama.get('cpus'))):>11}"
                     f"{fmt(int(ollama['pids']) if ollama.get('pids') else None):>11}{'shared':>11}")
        if om is None:
            problems.append("ollama: unlimited: the shared Ollama has no memory ceiling")
            unlimited = True
        else:
            tot["mem"] += om
        tot["mem_res"] += orr
    guaranteed = tot["mem_res"] + bx["host_reserve_mb"]
    lines.append(f"box: guaranteed memory {guaranteed}M of {bx['mem_mb']}M ({guaranteed / bx['mem_mb']:.0%}, host reserve "
                 f"{bx['host_reserve_mb']}M included)")
    if guaranteed > bx["mem_mb"]:
        problems.append(f"box: reservations {guaranteed}M are more than the box's {bx['mem_mb']}M (overcommitted)")
    if not unlimited:
        ratio = (tot["mem"] + bx["host_reserve_mb"]) / bx["mem_mb"]
        lines.append(f"box: memory ceilings sum to {tot['mem'] + bx['host_reserve_mb']}M, {ratio:.2f}x the box "
                     f"(bound {bx['max_overcommit']:g}x); cpu limits sum to {tot['cpus']:g} of {bx['cpus']}")
        if ratio > bx["max_overcommit"]:
            problems.append(f"box: memory ceilings are {ratio:.2f}x the box, over the {bx['max_overcommit']:g}x bound")
    disk = tot["disk"] + bx["disk_reserve_gb"]
    lines.append(f"box: disk quotas {tot['disk']:g}G + shared reserve {bx['disk_reserve_gb']}G = {disk:g}G of {bx['disk_gb']}G")
    if disk > bx["disk_gb"]:
        problems.append(f"box: disk quotas and reserve {disk:g}G are more than the disk's {bx['disk_gb']}G")
    return lines, problems


# ---------------------------------------------------------------- disk ----
def _du_mb(path: str) -> int:
    if not os.path.exists(path):
        return 0
    r = subprocess.run(["du", "-sxm", path], capture_output=True, text=True)
    try:
        return int(r.stdout.split()[0])
    except (IndexError, ValueError):
        return 0


def member_volumes(m: str) -> list[str]:
    if not shutil.which("docker"):
        return []
    r = subprocess.run(["docker", "volume", "ls", "-q", "--filter", f"label=com.docker.compose.project=brain-{m}"],
                       capture_output=True, text=True)
    out = []
    for v in r.stdout.split():
        i = subprocess.run(["docker", "volume", "inspect", "-f", "{{.Mountpoint}}", v], capture_output=True, text=True)
        if i.stdout.strip():
            out.append(i.stdout.strip())
    return out


def disk(names: list[str], brains_root: Path, quota_gb: float, home: str = "/home", fs: str = "/") -> tuple[list[str], list[str]]:
    lines, problems = [f"{'member':<12}{'used MB':>10}{'quota MB':>10}"], []
    for m in names:
        paths = [str(brains_root / m), f"{home}/{m}-cc", f"{home}/{m}-hands", *member_volumes(m)]
        used = sum(_du_mb(p) for p in paths)
        q = int(quota_gb * 1024)
        lines.append(f"{m:<12}{used:>10}{q:>10}")
        if used > q:
            problems.append(f"{m}: {used} MB used, over its {q} MB quota")
    st = os.statvfs(fs)
    free = st.f_bavail / st.f_blocks * 100 if st.f_blocks else 100
    lines.append(f"box: {free:.0f}% of {fs} free")
    if free < BOX["min_free_pct"]:
        problems.append(f"box: only {free:.0f}% of {fs} free (alarm under {BOX['min_free_pct']}%)")
    return lines, problems


# ---------------------------------------------------------------- cli ----
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="member_limits.py", description="per-member limits on a shared box (prints only)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("profile")
    o = sub.add_parser("override")
    o.add_argument("--update-tab", metavar="DIR")
    mg = sub.add_parser("merge")
    mg.add_argument("file")
    mg.add_argument("--admin", action="store_true")
    u = sub.add_parser("unit")
    u.add_argument("member")
    u.add_argument("kind", choices=("slice", "bridge", "term", "env"))
    pa = sub.add_parser("parent")
    pa.add_argument("kind", choices=("brain", "system"))
    pa.add_argument("members_tsv", nargs="?")
    pa.add_argument("--brains-root", default=os.environ.get("BRAINS_ROOT", "/srv/brains"))
    pa.add_argument("--add", type=int, default=0, help="also count N more members")
    pa.add_argument("--no-admin", action="store_true")
    for name in ("check", "disk"):
        c = sub.add_parser(name)
        c.add_argument("members_tsv", nargs="?")
        c.add_argument("--members", dest="members_opt")
        c.add_argument("--brains-root", default=os.environ.get("BRAINS_ROOT", "/srv/brains"))
        if name == "check":
            c.add_argument("--plan", action="store_true", help="every member with the profile (after apply)")
            c.add_argument("--admin-dir", default=os.environ.get("ADMIN_BRAIN_DIR", "/home/hbar/brain"))
            c.add_argument("--no-admin", action="store_true", help="no first brain on this box")
            c.add_argument("--systemd-dir", default=os.environ.get("SYSTEMD_DIR", "/etc/systemd/system"))
            c.add_argument("--limits-dir", default=os.environ.get("LIMITS_DIR", LIMITS_DIR))
            c.add_argument("--add", type=int, default=0, help="also count N more members with the profile")
    a = ap.parse_args(argv)
    try:
        p = profile()
        bx = box()
    except ValueError as e:
        print(f"refused: {e}", file=sys.stderr)
        return 2
    if a.cmd == "profile":
        print(json.dumps(p, indent=1))
        return 0
    if a.cmd == "override":
        sys.stdout.write(member_override(p, a.update_tab))
        return 0
    if a.cmd == "merge":
        text = sys.stdin.read() if a.file == "-" else (Path(a.file).read_text() if Path(a.file).exists() else "")
        sys.stdout.write(merge_override(text, p, admin=a.admin))
        return 0
    if a.cmd == "unit":
        if a.member != "admin" and not re.fullmatch(r"[a-z][a-z0-9]{1,15}", a.member):
            print(f"refused: bad handle {a.member!r}", file=sys.stderr)
            return 2
        sys.stdout.write(unit_text(a.member, a.kind, p, os.environ.get("LIMITS_DIR", LIMITS_DIR)))
        return 0
    root = Path(a.brains_root)
    tsv = Path(a.members_tsv or getattr(a, "members_opt", None) or root / "members.tsv")
    if a.cmd == "parent":
        sys.stdout.write(parent_text(a.kind, len(members(tsv)) + a.add + (0 if a.no_admin else 1), p))
        return 0
    names = members(tsv)
    if a.cmd == "disk":
        lines, problems = disk(names, root, p["disk_gb"])
    else:
        tenants, ollama = {}, None
        if not a.no_admin:
            if a.plan:
                tenants["admin"], ollama = tenant_from_profile(p), dict(p["ollama"])
            else:
                t = tenant_from_box("admin", Path(a.admin_dir) / "docker-compose.override.yml", Path(a.systemd_dir),
                                    Path(a.limits_dir), p)
                ollama = t.pop("ollama")
                tenants["admin"] = t
        for m in names:
            if a.plan:
                tenants[m] = tenant_from_profile(p)
            else:
                t = tenant_from_box(m, root / m / "docker-compose.override.yml", Path(a.systemd_dir), Path(a.limits_dir), p)
                t.pop("ollama")
                tenants[m] = t
        for i in range(a.add):
            tenants[f"new{i + 1}"] = tenant_from_profile(p)
        print(f"{'plan' if a.plan else 'as set'}: {len(names)} members from {tsv}"
              f"{'' if a.no_admin else ' + the admin brain'}{f' + {a.add} new' if a.add else ''}; box {bx['cpus']} cpus, "
              f"{bx['mem_mb']}M, {bx['disk_gb']}G")
        lines, problems = check(tenants, ollama, bx)
    print("\n".join(lines))
    for pr in problems:
        print(f"FAIL {pr}")
    print("limits: " + ("FAIL" if problems else "OK"))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
