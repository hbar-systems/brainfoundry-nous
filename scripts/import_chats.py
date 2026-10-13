#!/usr/bin/env python3
"""Import a person's ChatGPT or Claude export into their brain, through the gate.

Five steps, each a subcommand (docs/IMPORT.md, 2026-10-13):

  prep     <export.zip | dir | conversations.json> <out_dir>
           one markdown document per conversation (title, date, role-labelled
           turns, main branch only, nothing cut) plus out_dir/index.tsv
  list     <out_dir> [filters]       date, size, title of every conversation
  select   <out_dir> [filters]       writes out_dir/manifest.tsv and prints its id
  propose  <out_dir> --api URL       permit, then one proposal per manifest row (PENDING)
  approve  <out_dir> --api URL --yes <manifest_id>
           the person's one yes: hashes re-checked, then the brain's own
           server-side approve (POST /documents/approve-all) for exactly the
           manifest's proposal ids

Nothing here writes memory directly. propose goes through /documents/upload
(permit required, injection scan on every document); approve only works on
proposals the brain already holds as PENDING. BRAIN_API_KEY comes from the
environment.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import sys
import time
import zipfile

INDEX_COLS = ["id", "source", "kind", "date", "updated", "title", "turns", "chars", "file", "sha256"]
STATE_COLS = ["id", "sha256", "proposal_id", "permit_id", "injection_risk"]


# ── reading the export ────────────────────────────────────────────────────

def load_export(src):
    """Return (conversations, projects) from a zip, a directory or a json file.
    ChatGPT may shard into conversations-000.json, ...; all shards are read."""
    src = pathlib.Path(src).expanduser()
    convs, projects = [], []

    def take(name, raw):
        data = json.loads(raw)
        base = name.rsplit("/", 1)[-1]
        if base == "projects.json":
            projects.extend(data if isinstance(data, list) else [])
        elif isinstance(data, list):
            convs.extend(data)
        elif isinstance(data, dict):  # older or hand-made shapes
            convs.extend(data.get("conversations") or data.get("items") or [])

    def wanted(name):
        base = name.rsplit("/", 1)[-1]
        return base == "projects.json" or re.fullmatch(r"conversations(-\d+)?\.json", base)

    if src.is_file() and zipfile.is_zipfile(src):
        with zipfile.ZipFile(src) as z:
            for n in sorted(z.namelist()):
                if wanted(n) and "__MACOSX" not in n:
                    take(n, z.read(n))
    elif src.is_dir():
        for p in sorted(src.rglob("*.json")):
            if wanted(p.name) and "__MACOSX" not in p.parts:
                take(p.name, p.read_bytes())
    elif src.is_file():
        take(src.name, src.read_bytes())
    else:
        raise SystemExit(f"not found: {src}")
    return convs, projects


def _iso(ts):
    """epoch float (ChatGPT) or ISO string (Claude) -> (YYYY-MM-DD, full ISO) or ('', '')."""
    if ts in (None, ""):
        return "", ""
    try:
        if isinstance(ts, (int, float)):
            d = dt.datetime.fromtimestamp(float(ts), tz=dt.timezone.utc)
        else:
            d = dt.datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
            if d.tzinfo is None:
                d = d.replace(tzinfo=dt.timezone.utc)
        d = d.astimezone(dt.timezone.utc)
        return d.strftime("%Y-%m-%d"), d.strftime("%Y-%m-%dT%H:%M:%SZ")
    except (ValueError, OSError, OverflowError):
        return "", ""


def _chatgpt_text(msg):
    content = msg.get("content") or {}
    ctype = content.get("content_type", "text")
    if ctype not in ("text", "multimodal_text"):
        return ""  # code to tools, execution output, browsing, reasoning traces
    out = []
    for p in content.get("parts") or []:
        if isinstance(p, str):
            out.append(p)
        elif isinstance(p, dict):
            if isinstance(p.get("text"), str):
                out.append(p["text"])
            elif p.get("content_type", "").endswith("asset_pointer"):
                out.append("[image]")
    return "\n".join(x for x in out if x).strip()


def chatgpt_turns(conv):
    """Main branch only: walk from current_node up through parents. Without
    current_node, follow the last child from the root (the latest regeneration)."""
    mapping = conv.get("mapping") or {}
    chain = []
    node = conv.get("current_node")
    if node not in mapping:
        roots = [k for k, v in mapping.items() if not v.get("parent") or v.get("parent") not in mapping]
        node = roots[0] if roots else None
        while node and (mapping[node].get("children") or []):
            node = mapping[node]["children"][-1]
    seen = set()
    while node and node in mapping and node not in seen:
        seen.add(node)
        chain.append(mapping[node])
        node = mapping[node].get("parent")
    turns = []
    for n in reversed(chain):
        m = n.get("message")
        if not m:
            continue
        role = (m.get("author") or {}).get("role")
        meta = m.get("metadata") or {}
        if role not in ("user", "assistant") or meta.get("is_visually_hidden_from_conversation"):
            continue
        if m.get("recipient", "all") != "all":
            continue
        text = _chatgpt_text(m)
        if text:
            turns.append((role, _iso(m.get("create_time"))[1], text))
    return turns


def claude_turns(conv):
    turns = []
    for m in conv.get("chat_messages") or []:
        text = m.get("text") or ""
        if not text.strip():
            text = "\n".join(b.get("text", "") for b in (m.get("content") or [])
                             if isinstance(b, dict) and b.get("type") == "text")
        for a in m.get("attachments") or []:
            if a.get("extracted_content"):
                text += f"\n\n[attachment: {a.get('file_name', 'file')}]\n{a['extracted_content']}"
        role = "user" if m.get("sender") == "human" else "assistant"
        if text.strip():
            turns.append((role, _iso(m.get("created_at"))[1], text.strip()))
    return turns


def normalize(conv):
    """One conversation from either export -> dict(id, source, date, updated, title, turns)."""
    if "mapping" in conv:
        return {"id": conv.get("conversation_id") or conv.get("id") or "", "source": "chatgpt",
                "date": _iso(conv.get("create_time"))[0], "updated": _iso(conv.get("update_time"))[1],
                "title": conv.get("title") or "", "turns": chatgpt_turns(conv)}
    if "chat_messages" in conv:
        return {"id": conv.get("uuid") or "", "source": "claude",
                "date": _iso(conv.get("created_at"))[0], "updated": _iso(conv.get("updated_at"))[1],
                "title": conv.get("name") or "", "turns": claude_turns(conv)}
    return None


def _slug(s, n=48):
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return (s[:n].rstrip("-")) or "untitled"


def _one_line(s):
    return " ".join(str(s).split()).replace("\t", " ")


ROLE_LABEL = {"user": "Me", "assistant": "Assistant"}


def render(c):
    head = [f"# {c['title'] or 'Untitled'}", "",
            f"Source: {c['source']} export, conversation {c['id']}",
            f"Started: {c['date'] or 'unknown'}" + (f"; last turn {c['updated']}" if c.get("updated") else ""),
            ""]
    body = []
    for role, when, text in c["turns"]:
        label = ROLE_LABEL[role] + (" (" + c["source"].capitalize() + ")" if role == "assistant" else "")
        body += [f"## {label}" + (f", {when}" if when else ""), "", text, ""]
    return "\n".join(head + body)


def prep(src, out_dir):
    out = pathlib.Path(out_dir)
    (out / "docs").mkdir(parents=True, exist_ok=True)
    convs, projects = load_export(src)
    rows = []
    for raw in convs:
        c = normalize(raw) if isinstance(raw, dict) else None
        if not c or not c["turns"]:
            continue
        cid = c["id"] or hashlib.sha256(json.dumps(raw, sort_keys=True).encode()).hexdigest()[:16]
        c["id"] = cid
        name = f"{c['source']}_{c['date'] or 'undated'}_{_slug(c['title'])}_{cid.replace('-', '')[:8]}.md"
        text = render(c)
        (out / "docs" / name).write_text(text, encoding="utf-8")
        rows.append({"id": cid, "source": c["source"], "kind": "conversation", "date": c["date"],
                     "updated": c.get("updated", ""), "title": _one_line(c["title"]), "turns": len(c["turns"]),
                     "chars": len(text), "file": f"docs/{name}",
                     "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()})
    for p in projects:
        parts = [f"# Project: {p.get('name') or 'Untitled'}", ""]
        if p.get("description"):
            parts += [p["description"], ""]
        if p.get("prompt_template"):
            parts += ["## Standing instructions", "", p["prompt_template"], ""]
        for d in p.get("docs") or []:
            parts += [f"## Document: {d.get('filename', 'doc')}", "", d.get("content", ""), ""]
        if len(parts) <= 2:
            continue
        pid = p.get("uuid") or _slug(p.get("name") or "project")
        date = _iso(p.get("created_at"))[0]
        name = f"claude-project_{date or 'undated'}_{_slug(p.get('name') or '')}_{pid.replace('-', '')[:8]}.md"
        text = "\n".join(parts)
        (out / "docs" / name).write_text(text, encoding="utf-8")
        rows.append({"id": pid, "source": "claude", "kind": "project", "date": date,
                     "updated": _iso(p.get("updated_at"))[1], "title": _one_line(p.get("name") or ""),
                     "turns": 0, "chars": len(text), "file": f"docs/{name}",
                     "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()})
    rows.sort(key=lambda r: (r["date"], r["updated"], r["id"]), reverse=True)
    write_tsv(out / "index.tsv", INDEX_COLS, rows)
    return rows


# ── tsv files ─────────────────────────────────────────────────────────────

def write_tsv(path, cols, rows, comments=()):
    lines = [f"# {c}" for c in comments] + ["\t".join(cols)]
    lines += ["\t".join(_one_line(r.get(k, "")) for k in cols) for r in rows]
    pathlib.Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def read_tsv(path):
    path = pathlib.Path(path)
    if not path.exists():
        return []
    lines = [l for l in path.read_text(encoding="utf-8").splitlines() if l and not l.startswith("#")]
    if not lines:
        return []
    cols = lines[0].split("\t")
    return [dict(zip(cols, l.split("\t"))) for l in lines[1:]]


# ── selection ─────────────────────────────────────────────────────────────

def _read_list(path):
    """One entry per line: a conversation id, a doc file name, or a prefix of either. # comments."""
    if not path:
        return None
    items = []
    for line in pathlib.Path(path).read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            items.append(line.split("\t", 1)[0])
    return items


def _matches(row, items):
    fname = row["file"].rsplit("/", 1)[-1]
    return any(row["id"].startswith(i) or fname.startswith(i) or row["file"] == i for i in items)


def select_rows(rows, since=None, until=None, include=None, exclude=None, newest=None,
                with_projects=False, max_chars=None):
    """include is a whitelist (only these), exclude strikes rows; dates are inclusive."""
    out = []
    for r in rows:
        if r["kind"] == "project" and not with_projects and not (include and _matches(r, include)):
            continue
        if since and (not r["date"] or r["date"] < since):
            continue
        if until and (not r["date"] or r["date"] > until):
            continue
        if include is not None and not _matches(r, include):
            continue
        if exclude and _matches(r, exclude):
            continue
        if max_chars and int(r["chars"]) > max_chars:
            continue
        out.append(r)
    out.sort(key=lambda r: (r["date"], r["updated"], r["id"]), reverse=True)
    return out[:newest] if newest else out


def manifest_id(rows):
    """Names the selection: the hash over (id, document hash) of every row, order-free."""
    h = hashlib.sha256("\n".join(sorted(f"{r['id']}\t{r['sha256']}" for r in rows)).encode())
    return h.hexdigest()[:16]


def _filters(a):
    return dict(since=a.since, until=a.until, include=_read_list(a.include), exclude=_read_list(a.exclude),
                newest=a.newest, with_projects=a.with_projects, max_chars=a.max_chars)


def _fmt_size(n):
    n = int(n)
    return f"{n / 1000:.0f}k" if n >= 1000 else str(n)


def print_table(rows, file=sys.stdout):
    for r in rows:
        print(f"{r['date'] or 'undated':10}  {_fmt_size(r['chars']):>6}  {r['source']:7}  "
              f"{r['id'][:12]:12}  {r['title'][:70]}", file=file)
    total = sum(int(r["chars"]) for r in rows)
    print(f"{len(rows)} documents, {total:,} characters", file=file)


# ── the brain, through its gate ───────────────────────────────────────────

class Brain:
    """The three API calls the import uses. Tests swap in a fake."""

    def __init__(self, api, key):
        import requests
        self.r, self.api, self.h = requests, api.rstrip("/"), {"X-Api-Key": key} if key else {}

    def permit(self):
        resp = self.r.post(f"{self.api}/documents/upload/permit", headers=self.h, timeout=15)
        resp.raise_for_status()
        return resp.json()["permit_id"]

    def propose(self, permit_id, name, data, layer=None):
        form = {"permit_id": permit_id}
        if layer:
            form["layer"] = layer
        resp = self.r.post(f"{self.api}/documents/upload", headers=self.h, data=form,
                           files={"file": (name, data, "text/markdown")}, timeout=120)
        # An expired permit comes back from NodeOS as 403/404, wrapped by the api as 502
        # "NodeOS proposal failed"; one retry with a fresh permit (bounded by the caller).
        if resp.status_code in (403, 404, 502) and ("ermit" in resp.text or "NodeOS proposal failed" in resp.text):
            return {"permit_expired": True}
        resp.raise_for_status()
        return resp.json()

    def approve(self, proposal_ids):
        resp = self.r.post(f"{self.api}/documents/approve-all", headers=self.h,
                           json={"proposal_ids": proposal_ids}, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def approve_status(self):
        resp = self.r.get(f"{self.api}/documents/approve-all/status", headers=self.h, timeout=15)
        resp.raise_for_status()
        return resp.json()


PERMIT_REFRESH_S = 240  # NodeOS upload permits live 300 s


def propose_manifest(out_dir, brain, layer=None, log=print):
    """One proposal per manifest row, resumable: rows already proposed are skipped."""
    out = pathlib.Path(out_dir)
    rows = read_tsv(out / "manifest.tsv")
    if not rows:
        raise SystemExit("no manifest.tsv; run select first")
    state = {s["id"]: s for s in read_tsv(out / "proposals.tsv")}
    permit, got = None, 0.0
    for i, r in enumerate(rows, 1):
        done = state.get(r["id"])
        if done and done["sha256"] == r["sha256"] and done["proposal_id"]:
            continue
        data = (out / r["file"]).read_bytes()
        if hashlib.sha256(data).hexdigest() != r["sha256"]:
            raise SystemExit(f"{r['file']} changed since select; run select again")
        for _ in range(2):
            if not permit or time.monotonic() - got > PERMIT_REFRESH_S:
                permit, got = brain.permit(), time.monotonic()
            res = brain.propose(permit, r["file"].rsplit("/", 1)[-1], data, layer)
            if not res.get("permit_expired"):
                break
            permit = None
        else:
            raise SystemExit("the brain refused two fresh permits; stopping")
        risk = ((res.get("injection_scan") or {}).get("risk")) or ""
        state[r["id"]] = {"id": r["id"], "sha256": r["sha256"], "proposal_id": res["proposal_id"],
                          "permit_id": permit, "injection_risk": risk}
        write_tsv(out / "proposals.tsv", STATE_COLS, list(state.values()))  # after every row: resumable
        log(f"[{i}/{len(rows)}] proposed {r['file']} {res['proposal_id'][:8]}" + (f" risk={risk}" if risk else ""))
    return state


SAFE_RISK = ("", "none", "low")


def approve_manifest(out_dir, brain, yes, include_flagged=False, poll=2.0, log=print):
    """The person's one yes for a named manifest. Refuses unless yes == the manifest id
    computed now from the files on disk, every row is proposed, and every document still
    hashes to what was selected."""
    out = pathlib.Path(out_dir)
    rows = read_tsv(out / "manifest.tsv")
    mid = manifest_id(rows)
    if yes != mid:
        raise SystemExit(f"--yes {yes} does not name this manifest (its id is {mid}); nothing approved")
    state = {s["id"]: s for s in read_tsv(out / "proposals.tsv")}
    ids, flagged = [], []
    for r in rows:
        if hashlib.sha256((out / r["file"]).read_bytes()).hexdigest() != r["sha256"]:
            raise SystemExit(f"{r['file']} changed since select; nothing approved")
        s = state.get(r["id"])
        if not s or s["sha256"] != r["sha256"] or not s["proposal_id"]:
            raise SystemExit(f"{r['file']} not proposed yet; run propose first; nothing approved")
        if s["injection_risk"] not in SAFE_RISK:
            flagged.append((r, s["injection_risk"]))
            if not include_flagged:
                continue
        ids.append(s["proposal_id"])
    for r, risk in flagged:
        log(f"flagged ({risk}): {r['file']}" + ("" if include_flagged else "  left PENDING"))
    if not ids:
        raise SystemExit("nothing to approve")
    res = brain.approve(ids)
    log(f"approve sent for {len(ids)} proposals (manifest {mid})")
    while res.get("running"):
        time.sleep(poll)
        res = brain.approve_status()
        log(f"  {res.get('done')}/{res.get('total')} {res.get('current') or ''}")
    record = {"manifest_id": mid, "approved_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
              "proposals": len(ids), "left_pending_flagged": 0 if include_flagged else len(flagged),
              "failed": res.get("failed") or []}
    (out / "approval.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return record


# ── command line ──────────────────────────────────────────────────────────

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prep"); p.add_argument("src"); p.add_argument("out_dir")
    for name in ("list", "select"):
        p = sub.add_parser(name); p.add_argument("out_dir")
        p.add_argument("--since", help="YYYY-MM-DD, inclusive"); p.add_argument("--until", help="YYYY-MM-DD, inclusive")
        p.add_argument("--include", help="file: only these ids/doc names"); p.add_argument("--exclude", help="file: strike these")
        p.add_argument("--newest", type=int); p.add_argument("--max-chars", type=int)
        p.add_argument("--with-projects", action="store_true", help="include Claude project docs")
    for name in ("propose", "approve"):
        p = sub.add_parser(name); p.add_argument("out_dir")
        p.add_argument("--api", default=os.getenv("API_BASE", "http://localhost:8010"))
    sub.choices["propose"].add_argument("--layer")
    sub.choices["approve"].add_argument("--yes", required=True, help="the manifest id printed by select")
    sub.choices["approve"].add_argument("--include-flagged", action="store_true")
    a = ap.parse_args(argv)

    if a.cmd == "prep":
        rows = prep(a.src, a.out_dir)
        print_table(rows[:20])
        print(f"index: {pathlib.Path(a.out_dir) / 'index.tsv'} (newest 20 shown; `list` for all)")
    elif a.cmd in ("list", "select"):
        rows = select_rows(read_tsv(pathlib.Path(a.out_dir) / "index.tsv"), **_filters(a))
        print_table(rows)
        if a.cmd == "select":
            mid = manifest_id(rows)
            write_tsv(pathlib.Path(a.out_dir) / "manifest.tsv", INDEX_COLS, rows,
                      comments=[f"manifest_id: {mid}", f"selected: {dt.date.today().isoformat()}",
                                f"filters: {json.dumps({k: v for k, v in vars(a).items() if k not in ('cmd', 'out_dir') and v})}"])
            print(f"manifest: {pathlib.Path(a.out_dir) / 'manifest.tsv'}  id {mid}")
    else:
        brain = Brain(a.api, os.getenv("BRAIN_API_KEY", ""))
        if a.cmd == "propose":
            propose_manifest(a.out_dir, brain, layer=a.layer)
            print(f"proposed; the person approves with: approve {a.out_dir} --yes "
                  f"{manifest_id(read_tsv(pathlib.Path(a.out_dir) / 'manifest.tsv'))}")
        else:
            print(json.dumps(approve_manifest(a.out_dir, brain, a.yes, a.include_flagged), indent=2))


if __name__ == "__main__":
    main()
