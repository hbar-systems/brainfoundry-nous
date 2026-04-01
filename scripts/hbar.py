#!/usr/bin/env python3
"""
hbar — minimal NodeOS operator CLI

Read commands:
    python scripts/hbar.py status
    python scripts/hbar.py proposals [--status PENDING]
    python scripts/hbar.py proposal get <id>
    python scripts/hbar.py permits [--status ACTIVE]
    python scripts/hbar.py permit get <id>
    python scripts/hbar.py audit [--limit N]

Write commands:
    python scripts/hbar.py permit request --agent-id <str> --loop-type <str> \\
        --scopes git.preview,git.commit --reason <str> [--ttl 3600] [--node-id <str>]
    python scripts/hbar.py propose write <permit_id> --path <str> --content <str>
    python scripts/hbar.py propose commit <permit_id> --message <str> [--path <file> ...]
    python scripts/hbar.py propose preview <permit_id> [--max-bytes 20000]
    python scripts/hbar.py propose push <permit_id> --branch <str> --commit-hash <str> \\
        --preview-snapshot <proposal_id> [--remote origin]

    python scripts/hbar.py --json <command>   # raw JSON output

Environment:
    HBAR_NODEOS_URL   NodeOS base URL (default: http://localhost:8001)
"""

import argparse
import json
import os
import sys
from urllib.parse import urljoin

import requests

NODEOS_URL = os.getenv("HBAR_NODEOS_URL", "http://localhost:8001")


# ---------------------------------------------------------------------------
# HTTP client
# ---------------------------------------------------------------------------

def get(path: str, params: dict = None, timeout: float = 8.0) -> dict:
    url = urljoin(NODEOS_URL.rstrip("/") + "/", path.lstrip("/"))
    try:
        r = requests.get(url, params=params, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.ConnectionError:
        print(f"error: cannot reach NodeOS at {NODEOS_URL}", file=sys.stderr)
        sys.exit(1)
    except requests.exceptions.HTTPError as e:
        print(f"error: {e.response.status_code} from {url}", file=sys.stderr)
        sys.exit(1)
    except requests.exceptions.Timeout:
        print(f"error: timeout connecting to {url}", file=sys.stderr)
        sys.exit(1)


def post(path: str, body: dict, timeout: float = 8.0) -> dict:
    url = urljoin(NODEOS_URL.rstrip("/") + "/", path.lstrip("/"))
    try:
        r = requests.post(url, json=body, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.ConnectionError:
        print(f"error: cannot reach NodeOS at {NODEOS_URL}", file=sys.stderr)
        sys.exit(1)
    except requests.exceptions.HTTPError as e:
        try:
            detail = e.response.json().get("detail", e.response.text)
        except Exception:
            detail = e.response.text
        print(f"error: {e.response.status_code} — {detail}", file=sys.stderr)
        sys.exit(1)
    except requests.exceptions.Timeout:
        print(f"error: timeout connecting to {url}", file=sys.stderr)
        sys.exit(1)


def _fetch_node_id() -> str:
    """Derive node_id from live NodeOS state rather than assuming a value."""
    data = get("/v1/operator/overview")
    node_id = data.get("node", {}).get("node_id")
    if not node_id:
        print("error: could not derive node_id from NodeOS — use --node-id explicitly", file=sys.stderr)
        sys.exit(1)
    return node_id


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------

def _row(label: str, value) -> str:
    return f"  {label:<28} {value}"


def fmt_status(d: dict) -> str:
    node = d.get("node", {})
    repo = d.get("repo", {})
    counts = d.get("counts", {})
    lines = [
        "=== NodeOS Status ===",
        _row("node_id", node.get("node_id", "-")),
        _row("health", node.get("health", "-")),
        "",
        "--- repo ---",
        _row("branch", repo.get("branch", "-")),
        _row("head", repo.get("head", "-")[:12] if repo.get("head") else "-"),
        _row("remote_head", repo.get("remote_head", "-")[:12] if repo.get("remote_head") else "-"),
        _row("ahead / behind", f"{repo.get('ahead', 0)} / {repo.get('behind', 0)}"),
        "",
        "--- counts ---",
        _row("pending_proposals", counts.get("pending_proposals", 0)),
        _row("active_permits", counts.get("active_permits", 0)),
        _row("recent_approvals", counts.get("recent_approvals", 0)),
        _row("recent_failures", counts.get("recent_failures", 0)),
    ]
    return "\n".join(lines)


def fmt_proposals(d: dict) -> str:
    items = d.get("items", [])
    total = d.get("count", len(items))
    lines = [f"=== Proposals ({total}) ==="]
    if not items:
        lines.append("  (none)")
        return "\n".join(lines)
    for p in items:
        snap = p.get("preview_snapshot") or {}
        lines += [
            "",
            f"  [{p.get('status','?')}] {p.get('proposal_id','-')}",
            _row("action_type", p.get("action_type", "-")),
            _row("created_at", p.get("created_at", "-")),
            _row("permit_id", p.get("permit_id", "-")),
        ]
        if snap:
            lines.append(_row("branch (snap)", snap.get("branch", "-")))
            lines.append(_row("ahead/behind (snap)", f"{snap.get('ahead',0)}/{snap.get('behind',0)}"))
        if p.get("commit_hash"):
            lines.append(_row("commit_hash", p["commit_hash"][:12]))
    return "\n".join(lines)


def fmt_proposal_detail(d: dict) -> str:
    p = d.get("item", d.get("proposal", d if "proposal_id" in d else d))
    snap = p.get("preview_snapshot") or {}
    payload = p.get("payload", {})
    lines = [
        f"=== Proposal {p.get('proposal_id','-')} ===",
        _row("status", p.get("status", "-")),
        _row("action_type", p.get("action_type", "-")),
        _row("permit_id", p.get("permit_id", "-")),
        _row("created_at", p.get("created_at", "-")),
        _row("decided_at", p.get("decided_at", "-")),
        _row("decided_by", p.get("decided_by", "-")),
        _row("decision_note", p.get("decision_note", "-")),
    ]
    if payload:
        lines.append("")
        lines.append("--- payload ---")
        for k, v in payload.items():
            lines.append(_row(k, v))
    if snap:
        lines.append("")
        lines.append("--- git preview snapshot ---")
        lines.append(_row("branch", snap.get("branch", "-")))
        lines.append(_row("local_head", str(snap.get("local_head", "-"))[:12]))
        lines.append(_row("remote_head", str(snap.get("remote_head", "-"))[:12]))
        lines.append(_row("ahead / behind", f"{snap.get('ahead',0)} / {snap.get('behind',0)}"))
        lines.append(_row("will_fast_forward", snap.get("will_fast_forward", "-")))
    return "\n".join(lines)


def fmt_permits(d: dict) -> str:
    items = d.get("items", [])
    total = d.get("total", d.get("count", len(items)))
    lines = [f"=== Permits ({total}) ==="]
    if not items:
        lines.append("  (none)")
        return "\n".join(lines)
    for p in items:
        secs = p.get("seconds_remaining")
        ttl_str = f"{secs}s remaining" if secs is not None else "-"
        lines += [
            "",
            f"  [{p.get('status','?')}] {p.get('permit_id','-')}",
            _row("agent_id", p.get("agent_id", "-")),
            _row("loop_type", p.get("loop_type", "-")),
            _row("scopes", ", ".join(p.get("scopes", []))),
            _row("reason", p.get("reason", "-")),
            _row("ttl", ttl_str),
        ]
    return "\n".join(lines)


def fmt_permit_detail(d: dict) -> str:
    p = d.get("item", d.get("permit", d if "permit_id" in d else d))
    secs = p.get("seconds_remaining")
    ttl_str = f"{secs}s remaining" if secs is not None else "-"
    lines = [
        f"=== Permit {p.get('permit_id','-')} ===",
        _row("status", p.get("status", "-")),
        _row("agent_id", p.get("agent_id", "-")),
        _row("node_id", p.get("node_id", "-")),
        _row("loop_type", p.get("loop_type", "-")),
        _row("scopes", ", ".join(p.get("scopes", []))),
        _row("reason", p.get("reason", "-")),
        _row("expires_at_unix", p.get("expires_at_unix", "-")),
        _row("ttl", ttl_str),
        _row("created_at", p.get("created_at", "-")),
    ]
    return "\n".join(lines)


def fmt_permit_issued(d: dict) -> str:
    lines = [
        "=== Permit Issued ===",
        _row("permit_id", d.get("permit_id", "-")),
        _row("permit_token", d.get("permit_token", "-")),
        _row("expires_at_unix", d.get("expires_at_unix", "-")),
    ]
    return "\n".join(lines)


def fmt_proposal_created(d: dict, action_type: str) -> str:
    lines = [
        f"=== Proposal Created ({action_type}) ===",
        _row("proposal_id", d.get("proposal_id", "-")),
        _row("status", d.get("status", "-")),
    ]
    return "\n".join(lines)


def fmt_decision(d: dict) -> str:
    result = d.get("result", {})
    lines = [
        "=== Decision ===",
        _row("proposal_id", d.get("proposal_id", "-")),
        _row("status", d.get("status", "-")),
    ]
    if result:
        lines.append("")
        lines.append("--- result ---")
        for k, v in result.items():
            lines.append(_row(k, str(v)[:120]))
    return "\n".join(lines)


def fmt_audit(d: dict) -> str:
    items = d.get("items", d.get("events", []))
    total = d.get("count", len(items))
    lines = [f"=== Audit Events ({total}) ==="]
    if not items:
        lines.append("  (none)")
        return "\n".join(lines)
    for e in items:
        lines += [
            "",
            f"  {e.get('timestamp','-')}  [{e.get('outcome','?')}]",
            _row("event_type", e.get("event_type", "-")),
            _row("action", e.get("action", "-")),
            _row("agent_id", e.get("agent_id", "-")),
            _row("resource_id", e.get("resource_id", "-")),
        ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

def cmd_status(args):
    data = get("/v1/operator/overview")
    if args.json:
        print(json.dumps(data, indent=2))
    else:
        print(fmt_status(data))


def cmd_proposals(args):
    params = {}
    if args.status:
        params["status"] = args.status
    if args.limit:
        params["limit"] = args.limit
    data = get("/v1/operator/proposals", params=params)
    if args.json:
        print(json.dumps(data, indent=2))
    else:
        print(fmt_proposals(data))


def cmd_proposal_get(args):
    data = get(f"/v1/operator/proposals/{args.id}")
    if args.json:
        print(json.dumps(data, indent=2))
    else:
        print(fmt_proposal_detail(data))


def cmd_permits(args):
    params = {}
    if args.status:
        params["status"] = args.status
    if args.limit:
        params["limit"] = args.limit
    data = get("/v1/operator/permits", params=params)
    if args.json:
        print(json.dumps(data, indent=2))
    else:
        print(fmt_permits(data))


def cmd_permit_get(args):
    data = get(f"/v1/operator/permits/{args.id}")
    if args.json:
        print(json.dumps(data, indent=2))
    else:
        print(fmt_permit_detail(data))


def cmd_permit_request(args):
    node_id = args.node_id if args.node_id else _fetch_node_id()
    scopes = [s.strip() for s in args.scopes.split(",") if s.strip()]
    body = {
        "node_id": node_id,
        "agent_id": args.agent_id,
        "loop_type": args.loop_type,
        "ttl_seconds": args.ttl,
        "scopes": scopes,
        "reason": args.reason,
    }
    if args.trace_id:
        body["trace_id"] = args.trace_id
    data = post("/v1/loops/request", body)
    if args.json:
        print(json.dumps(data, indent=2))
    else:
        print(fmt_permit_issued(data))


def cmd_propose_write(args):
    body = {
        "permit_id": args.permit_id,
        "action_type": "write_file",
        "payload": {
            "path": args.path,
            "content": args.content,
            "mode": "create_or_overwrite",
        },
    }
    data = post("/v1/actions/propose", body)
    if args.json:
        print(json.dumps(data, indent=2))
    else:
        print(fmt_proposal_created(data, "write_file"))


def cmd_propose_commit(args):
    payload = {"message": args.message}
    if args.path:
        payload["paths"] = args.path
    body = {
        "permit_id": args.permit_id,
        "action_type": "git_commit",
        "payload": payload,
    }
    data = post("/v1/actions/propose", body)
    if args.json:
        print(json.dumps(data, indent=2))
    else:
        print(fmt_proposal_created(data, "git_commit"))


def cmd_propose_preview(args):
    payload = {}
    if args.max_bytes:
        payload["max_bytes"] = args.max_bytes
    body = {
        "permit_id": args.permit_id,
        "action_type": "git_diff_preview",
        "payload": payload,
    }
    data = post("/v1/actions/propose", body)
    if args.json:
        print(json.dumps(data, indent=2))
    else:
        print(fmt_proposal_created(data, "git_diff_preview"))


def cmd_propose_push(args):
    body = {
        "permit_id": args.permit_id,
        "action_type": "git_push",
        "payload": {
            "branch": args.branch,
            "commit_hash": args.commit_hash,
            "remote": args.remote,
            "repo_path": args.repo_path,
            "preview_snapshot": args.preview_snapshot,
        },
    }
    data = post("/v1/actions/propose", body)
    if args.json:
        print(json.dumps(data, indent=2))
    else:
        print(fmt_proposal_created(data, "git_push"))


def cmd_proposal_decide(args):
    decision = "APPROVE" if args.approve else "DENY"
    body = {
        "permit_id": args.permit_id,
        "decision": decision,
        "decided_by": args.decided_by,
    }
    if args.note:
        body["note"] = args.note
    data = post(f"/v1/actions/{args.proposal_id}/decide", body)
    if args.json:
        print(json.dumps(data, indent=2))
    else:
        print(fmt_decision(data))


def cmd_audit(args):
    params = {}
    if args.limit:
        params["limit"] = args.limit
    if args.event_type:
        params["event_type"] = args.event_type
    if args.outcome:
        params["outcome"] = args.outcome
    data = get("/v1/operator/audit", params=params)
    if args.json:
        print(json.dumps(data, indent=2))
    else:
        print(fmt_audit(data))


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="hbar",
        description="NodeOS operator CLI",
    )
    p.add_argument("--json", action="store_true", help="emit raw JSON instead of formatted output")
    p.add_argument("--url", default=NODEOS_URL, help="NodeOS base URL (overrides HBAR_NODEOS_URL)")

    sub = p.add_subparsers(dest="command", required=True)

    # status
    sub.add_parser("status", help="show NodeOS overview")

    # proposals
    sp_proposals = sub.add_parser("proposals", help="list action proposals")
    sp_proposals.add_argument("--status", help="filter by status (PENDING, APPROVED, DENIED, …)")
    sp_proposals.add_argument("--limit", type=int, default=50, help="max results (default 50)")

    # proposal get <id> / proposal decide <id>
    sp_proposal = sub.add_parser("proposal", help="proposal subcommands")
    sp_proposal_sub = sp_proposal.add_subparsers(dest="proposal_cmd", required=True)
    sp_proposal_get = sp_proposal_sub.add_parser("get", help="get a single proposal by ID")
    sp_proposal_get.add_argument("id", help="proposal_id")

    sp_decide = sp_proposal_sub.add_parser("decide", help="approve or deny a proposal (executes on approve)")
    sp_decide.add_argument("proposal_id", help="proposal_id to decide")
    sp_decide.add_argument("--permit-id", dest="permit_id", required=True, help="permit authorising this decision")
    sp_decide.add_argument("--decided-by", dest="decided_by", required=True, help="identity of the decision maker")
    sp_decide.add_argument("--note", default=None, help="optional decision note")
    grp = sp_decide.add_mutually_exclusive_group(required=True)
    grp.add_argument("--approve", action="store_true", help="approve and execute the proposal")
    grp.add_argument("--deny", action="store_true", help="deny the proposal")

    # permits
    sp_permits = sub.add_parser("permits", help="list permits")
    sp_permits.add_argument("--status", help="filter by status (ACTIVE, EXPIRED, REVOKED)")
    sp_permits.add_argument("--limit", type=int, default=50, help="max results (default 50)")

    # permit get <id> / permit request
    sp_permit = sub.add_parser("permit", help="permit subcommands")
    sp_permit_sub = sp_permit.add_subparsers(dest="permit_cmd", required=True)
    sp_permit_get = sp_permit_sub.add_parser("get", help="get a single permit by ID")
    sp_permit_get.add_argument("id", help="permit_id")

    sp_permit_req = sp_permit_sub.add_parser("request", help="request a new loop permit")
    sp_permit_req.add_argument("--agent-id", dest="agent_id", required=True, help="agent identity requesting the permit")
    sp_permit_req.add_argument("--loop-type", dest="loop_type", required=True,
                               choices=["governed_git", "research", "admin", "inbox_sweep", "music_assist"],
                               help="loop type")
    sp_permit_req.add_argument("--scopes", required=True,
                               help="comma-separated scopes e.g. git.preview,git.commit")
    sp_permit_req.add_argument("--reason", required=True, help="human-readable reason for this permit")
    sp_permit_req.add_argument("--ttl", type=int, default=3600, help="TTL in seconds (default 3600)")
    sp_permit_req.add_argument("--node-id", dest="node_id", default=None,
                               help="node identity (default: derived from live NodeOS)")
    sp_permit_req.add_argument("--trace-id", dest="trace_id", default=None, help="optional trace ID")

    # propose write / commit / preview / push
    sp_propose = sub.add_parser("propose", help="propose a governed action")
    sp_propose_sub = sp_propose.add_subparsers(dest="propose_cmd", required=True)

    sp_pw = sp_propose_sub.add_parser("write", help="propose a write_file action")
    sp_pw.add_argument("permit_id", help="permit_id authorising this action")
    sp_pw.add_argument("--path", required=True, help="file path (must be under write path allowlist)")
    sp_pw.add_argument("--content", required=True, help="file content")

    sp_pc = sp_propose_sub.add_parser("commit", help="propose a git_commit action")
    sp_pc.add_argument("permit_id", help="permit_id authorising this action")
    sp_pc.add_argument("--message", required=True, help="commit message")
    sp_pc.add_argument("--path", dest="path", action="append", metavar="FILE",
                       help="file to stage (repeatable; omit to stage all)")

    sp_pprev = sp_propose_sub.add_parser("preview", help="propose a git_diff_preview action")
    sp_pprev.add_argument("permit_id", help="permit_id authorising this action")
    sp_pprev.add_argument("--max-bytes", dest="max_bytes", type=int, default=None,
                          help="max diff bytes (default: NodeOS default 20000)")

    sp_ppush = sp_propose_sub.add_parser("push", help="propose a git_push action")
    sp_ppush.add_argument("permit_id", help="permit_id authorising this action")
    sp_ppush.add_argument("--branch", required=True, help="branch to push")
    sp_ppush.add_argument("--commit-hash", dest="commit_hash", required=True,
                          help="exact commit SHA to push")
    sp_ppush.add_argument("--preview-snapshot", dest="preview_snapshot", required=True,
                          help="proposal_id of the approved git_diff_preview (governance requirement)")
    sp_ppush.add_argument("--remote", default="origin", help="remote name (default: origin)")
    sp_ppush.add_argument("--repo-path", dest="repo_path", default="/data/repos/hbar-brain",
                          help="repo path inside NodeOS (default: /data/repos/hbar-brain)")

    # audit
    sp_audit = sub.add_parser("audit", help="show audit events")
    sp_audit.add_argument("--limit", type=int, default=50, help="max results (default 50)")
    sp_audit.add_argument("--event-type", dest="event_type", help="filter by event_type")
    sp_audit.add_argument("--outcome", help="filter by outcome (ok, error, …)")

    return p


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = build_parser()
    args = parser.parse_args()

    # Allow --url to override the module-level default at runtime
    global NODEOS_URL
    NODEOS_URL = args.url

    if args.command == "status":
        cmd_status(args)
    elif args.command == "proposals":
        cmd_proposals(args)
    elif args.command == "proposal":
        if args.proposal_cmd == "get":
            cmd_proposal_get(args)
        elif args.proposal_cmd == "decide":
            cmd_proposal_decide(args)
    elif args.command == "permits":
        cmd_permits(args)
    elif args.command == "permit":
        if args.permit_cmd == "get":
            cmd_permit_get(args)
        elif args.permit_cmd == "request":
            cmd_permit_request(args)
    elif args.command == "propose":
        if args.propose_cmd == "write":
            cmd_propose_write(args)
        elif args.propose_cmd == "commit":
            cmd_propose_commit(args)
        elif args.propose_cmd == "preview":
            cmd_propose_preview(args)
        elif args.propose_cmd == "push":
            cmd_propose_push(args)
    elif args.command == "audit":
        cmd_audit(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
