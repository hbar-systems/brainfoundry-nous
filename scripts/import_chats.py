#!/usr/bin/env python3
"""Import a person's AI chat history into their brain, through the gate.

ChatGPT and Claude (2026-10-13); Gemini, DeepSeek, Grok, Copilot and Le Chat
exports, plus any pasted or dropped conversation (text, markdown, html, pdf)
as one document, added 2026-11-16 (docs/IMPORT.md "Other AIs"). The vendor is
detected from the file itself; FORMATS says which shapes were confirmed.

Five steps, each a subcommand (docs/IMPORT.md, 2026-10-13):

  prep     <export.zip | dir | export file | pasted .txt/.md/.html/.pdf> <out_dir>
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
import csv
import datetime as dt
import hashlib
import html as _html
import io
import json
import os
import pathlib
import re
import sys
import time
import zipfile
from html.parser import HTMLParser

INDEX_COLS = ["id", "source", "kind", "date", "updated", "title", "turns", "chars", "file", "sha256"]
STATE_COLS = ["id", "sha256", "proposal_id", "permit_id", "injection_risk"]


# ── reading the export ────────────────────────────────────────────────────

# Which vendor formats were confirmed, and from where (2026-11-16). "verified" means the
# file shape was read from the vendor's own documentation or a real sample; False means the
# parser follows third-party descriptions (named in the note) and is written to be tolerant.
FORMATS = {
    "chatgpt": {"verified": True, "note": "conversations.json, mapping trees; real exports since 2026-10-13"},
    "claude": {"verified": True, "note": "conversations.json with chat_messages; real exports since 2026-10-13"},
    "gemini": {"verified": False, "note": "Takeout My Activity > Gemini Apps, MyActivity.json or .html. Steps from "
               "https://support.google.com/gemini/answer/16920332 and record fields from "
               "https://developers.google.com/data-portability/schema-reference/my_activity; the Gemini "
               "prompt/answer fields (title 'Prompted ...', safeHtmlItem, details Request/Response, "
               "userInteractions) are third-party descriptions, not in Google's docs"},
    "deepseek": {"verified": False, "note": "no vendor doc found; conversations.json with mapping trees whose "
                 "messages hold fragments (REQUEST/RESPONSE/THINK), as read by the open-source "
                 "https://github.com/akivacp/chatgpt-json-tree-viewer"},
    "grok": {"verified": False, "note": "no vendor doc found; prod-grok-backend.json {conversations:[{conversation, "
             "responses:[{response:{_id, parent_response_id, sender, message, create_time}}]}]} per "
             "https://portable-ai-memory.pages.dev/providers/grok/ and the viewer above"},
    "copilot": {"verified": False, "note": "CSV download verified at "
                "https://support.microsoft.com/en-us/privacy/manage-your-copilot-activity-history-in-the-privacy-dashboard "
                "(columns not listed there); columns Conversation,Time,Author,Message / "
                "CreatedAt,MessageContent,Author,ChatName / Timestamp,ClientApp,Prompt per "
                "https://portable-ai-memory.pages.dev/providers/microsoft/"},
    "lechat": {"verified": False, "note": "export at admin.mistral.ai/account/export "
               "(https://help.mistral.ai/en/articles/347623-how-do-i-export-my-data-from-le-chat), file shape not "
               "documented; json chat_messages with role/content as read by the viewer above; else the fallback"},
    "perplexity": {"verified": False, "note": "no documented bulk file format (account 'Export my data' or a "
                   "privacy request); threads come in through the fallback (Export as Markdown/PDF, or paste)"},
    "pasted": {"verified": True, "note": "our own fallback: text, markdown, html or pdf, one conversation"},
}

# How the assistant is named in "## Assistant (<name>)". ChatGPT and Claude keep the
# capitalize() spelling they have had since 2026-10-13 (documents already in memory).
DISPLAY = {"chatgpt": "Chatgpt", "claude": "Claude", "gemini": "Gemini", "deepseek": "DeepSeek",
           "grok": "Grok", "copilot": "Copilot", "perplexity": "Perplexity", "lechat": "Le Chat",
           "pasted": "AI"}

GAP_S = 30 * 60  # Gemini (and nameless Copilot rows) start a new conversation after 30 minutes quiet


def _wanted(name):
    base = name.rsplit("/", 1)[-1]
    return (base in ("projects.json", "prod-grok-backend.json")
            or re.fullmatch(r"conversations(-\d+)?\.json", base)
            or base.lower() in ("myactivity.json", "myactivity.html")
            or base.lower().endswith(".csv"))


def load_export(src):
    """Return (conversations, projects) from a zip, a directory or one export file.
    ChatGPT may shard into conversations-000.json, ...; all shards are read. A zip or
    folder with none of the known names has every .json tried (Le Chat's file name
    is not documented); normalize() drops what it does not recognise."""
    src = pathlib.Path(src).expanduser()
    convs, projects = [], []

    def take(name, raw):
        base = name.rsplit("/", 1)[-1]
        low = base.lower()
        if low.endswith(".csv"):
            convs.extend(copilot_conversations(raw))
            return
        if low.endswith((".html", ".htm")):
            convs.extend(gemini_html_conversations(raw))
            return
        data = json.loads(raw)
        if low == "myactivity.json" or _looks_like_gemini(data):
            convs.extend(gemini_conversations(data))
        elif base == "projects.json":
            projects.extend(data if isinstance(data, list) else [])
        elif isinstance(data, list):
            convs.extend(data)
        elif isinstance(data, dict):  # older or hand-made shapes; Grok's {"conversations": [...]}
            got = data.get("conversations") or data.get("items") or data.get("chats")
            convs.extend(got if isinstance(got, list) else [data])

    def prefer_json(names):
        """Takeout may carry MyActivity.html and .json side by side: read the json only."""
        dirs_with_json = {n.rsplit("/", 1)[0] for n in names if n.lower().endswith("myactivity.json")}
        return [n for n in names if not (n.lower().endswith("myactivity.html")
                                         and n.rsplit("/", 1)[0] in dirs_with_json)]

    def read_all(names, read):
        names = prefer_json([n for n in names if "__MACOSX" not in n])
        hits = [n for n in names if _wanted(n)]
        for n in hits:
            take(n, read(n))
        if not convs and not projects:
            for n in names:
                if n.lower().endswith(".json") and n not in hits:
                    try:
                        take(n, read(n))
                    except ValueError:
                        continue

    if src.is_file() and zipfile.is_zipfile(src):
        with zipfile.ZipFile(src) as z:
            read_all(sorted(n for n in z.namelist() if not n.endswith("/")), z.read)
    elif src.is_dir():
        paths = {str(p.relative_to(src)): p for p in sorted(src.rglob("*")) if p.is_file()}
        read_all(sorted(paths), lambda n: paths[n].read_bytes())
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


# ── other AIs (2026-11-16) ──────────────────────────────────────────────

class _Text(HTMLParser):
    """html -> plain text: block tags become line breaks, script and style dropped."""
    BLOCK = {"p", "br", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "pre", "blockquote", "hr", "table"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.skip, self.title, self._in_title = [], 0, "", False

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1
        elif tag == "title":
            self._in_title = True
        elif tag in self.BLOCK:
            self.out.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.skip = max(0, self.skip - 1)
        elif tag == "title":
            self._in_title = False
        elif tag in self.BLOCK:
            self.out.append("\n")

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif not self.skip:
            self.out.append(data)


def html_text(markup):
    """(plain text, <title>) of an html string; whitespace tidied, paragraphs kept."""
    p = _Text()
    p.feed(markup)
    p.close()
    lines = [" ".join(l.replace("\u202f", " ").replace("\xa0", " ").split()) for l in "".join(p.out).split("\n")]
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    return text, " ".join(p.title.split())


def _strings(obj, keys=("text", "content", "prompt", "message", "response")):
    """Text found in an unknown json value: strings under the usual text keys, else every string."""
    if isinstance(obj, str):
        try:
            return _strings(json.loads(obj), keys) if obj[:1] in "[{" else [obj]
        except ValueError:
            return [obj]
    found, every = [], []

    def walk(o, under):
        if isinstance(o, str):
            (found if under else every).append(o)
        elif isinstance(o, dict):
            for k, v in o.items():
                walk(v, under or k in keys)
        elif isinstance(o, list):
            for v in o:
                walk(v, under)
    walk(obj, False)
    return [x for x in (found or every) if x.strip()]


def _looks_like_gemini(data):
    return (isinstance(data, list) and data and isinstance(data[0], dict) and "time" in data[0]
            and any("Gemini" in str(e.get("header", "")) or "Gemini" in " ".join(map(str, e.get("products") or []))
                    for e in data[:50] if isinstance(e, dict)))


_GEMINI_CID = re.compile(r"gemini\.google\.com/(?:u/\d+/)?app/(?:c/)?([0-9A-Za-z_-]{6,})")


def _gemini_entry(e):
    """One My Activity record -> (conversation id or '', iso time, prompt, answer), or None."""
    if not isinstance(e, dict):
        return None
    tag = str(e.get("header", "")) + " " + " ".join(map(str, e.get("products") or []))
    if "Gemini" not in tag:
        return None  # a full My Activity export carries Search, YouTube, ...: only Gemini comes in
    prompt, answer = [], []
    for d in e.get("details") or []:
        if isinstance(d, dict) and d.get("value"):
            (prompt if str(d.get("name", "")).lower() == "request" else
             answer if str(d.get("name", "")).lower() == "response" else []).append(str(d["value"]))
    title = str(e.get("title") or "")
    if not prompt and title.startswith("Prompted "):
        prompt.append(title[len("Prompted "):])
    for item in e.get("safeHtmlItem") or []:
        if isinstance(item, dict) and item.get("html"):
            answer.append(html_text(item["html"])[0])
    for ui in e.get("userInteractions") or []:
        u = ui.get("userInteraction", ui) if isinstance(ui, dict) else {}
        if not prompt and u.get("request"):
            prompt += _strings(u["request"])
        if not answer and u.get("response"):
            answer += _strings(u["response"])
    prompt, answer = "\n".join(prompt).strip(), "\n\n".join(answer).strip()
    if not prompt and not answer:
        return None
    m = _GEMINI_CID.search(str(e.get("titleUrl") or ""))
    return (m.group(1) if m else "", _iso(e.get("time"))[1], prompt, answer)


def _group_gemini(items):
    """items: (cid, iso, prompt, answer). Same conversation id -> one conversation; without
    an id, a new conversation after GAP_S of quiet. Returns already-normalized dicts."""
    items = sorted((i for i in items if i), key=lambda i: i[1])
    groups, by_cid, last_t = [], {}, None
    for it in items:
        cid, when = it[0], it[1]
        if cid:
            if cid not in by_cid:
                by_cid[cid] = []
                groups.append((cid, by_cid[cid]))
            by_cid[cid].append(it)
            continue
        t = dt.datetime.fromisoformat(when.replace("Z", "+00:00")).timestamp() if when else None
        if last_t is None or t is None or t - last_t > GAP_S or groups[-1][0]:
            groups.append(("", []))
        groups[-1][1].append(it)
        last_t = t
    out = []
    for cid, its in groups:
        turns = []
        for _, when, prompt, answer in its:
            if prompt:
                turns.append(("user", when, prompt))
            if answer:
                turns.append(("assistant", when, answer))
        first = next((p for _, _, p, _ in its if p), "Gemini")
        gid = cid or "gemini-" + hashlib.sha256(f"{its[0][1]}\n{first}".encode()).hexdigest()[:12]
        out.append({"_norm": {"id": gid, "source": "gemini", "date": its[0][1][:10],
                              "updated": its[-1][1], "title": _one_line(first)[:80], "turns": turns}})
    return out


def gemini_conversations(data):
    """MyActivity.json (a list of records) -> conversations."""
    return _group_gemini(_gemini_entry(e) for e in (data if isinstance(data, list) else []))


_DATE_LINE = re.compile(r"^(?:[A-Z][a-z]{2,8}\.? \d{1,2}, \d{4}|\d{1,2} [A-Z][a-z]{2,8}\.? \d{4}),? "
                        r"\d{1,2}:\d{2}(?::\d{2})?(?: ?[AP]M)?(?: [A-Z]{2,5}|[ ]?[+-]\d{2}:?\d{2})?$")


def _gemini_html_time(line):
    s = re.sub(r" (?:[A-Z]{2,5}|[+-]\d{2}:?\d{2})$", "", line).replace(".", "")
    for fmt in ("%b %d, %Y, %I:%M:%S %p", "%b %d, %Y, %I:%M %p", "%B %d, %Y, %I:%M:%S %p",
                "%d %b %Y, %H:%M:%S", "%d %B %Y, %H:%M:%S", "%b %d, %Y, %H:%M:%S"):
        try:
            return dt.datetime.strptime(s, fmt).replace(tzinfo=dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            continue
    return ""


def gemini_html_conversations(raw):
    """MyActivity.html: one 'outer-cell' card per record: header, 'Prompted <text>', a date
    line, the answer, then 'Products:'. Times read as UTC (the page prints local time)."""
    markup = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw
    if "outer-cell" not in markup:
        return []
    items = []
    for card in markup.split('class="outer-cell')[1:]:
        m = _GEMINI_CID.search(_html.unescape(card))
        text, _ = html_text('<div class="outer-cell' + card)
        lines = [l for l in text.split("\n") if l.strip()]
        if not lines or "Gemini" not in lines[0]:  # the card's header names the product
            continue
        body = lines[1:]
        cut = next((i for i, l in enumerate(body) if l.startswith("Products:")), len(body))
        body = body[:cut]
        di = next((i for i, l in enumerate(body) if _DATE_LINE.match(l.strip())), None)
        if di is None:
            continue
        prompt = "\n".join(body[:di]).strip()
        if prompt.startswith("Prompted "):
            prompt = prompt[len("Prompted "):]
        answer = "\n".join(body[di + 1:]).strip()
        if prompt or answer:
            items.append((m.group(1) if m else "", _gemini_html_time(body[di].strip()), prompt, answer))
    return _group_gemini(items)


def _main_branch(nodes, parent_of, children_of, start=None):
    """Node ids along the kept branch: from start (the current node) up, or from the root
    down through the last child (the latest regeneration)."""
    if start not in nodes:
        roots = [k for k in nodes if not parent_of(k) or parent_of(k) not in nodes]
        node = roots[0] if roots else None
        while node and [c for c in children_of(node) if c in nodes]:
            node = [c for c in children_of(node) if c in nodes][-1]
        start = node
    chain, seen, node = [], set(), start
    while node and node in nodes and node not in seen:
        seen.add(node)
        chain.append(node)
        node = parent_of(node)
    return list(reversed(chain))


def deepseek_turns(conv):
    """mapping tree like ChatGPT's; each message holds fragments typed REQUEST (the person),
    RESPONSE (the answer), THINK or SEARCH (left out, as ChatGPT's reasoning is)."""
    mapping = conv.get("mapping") or {}
    ids = _main_branch(mapping, lambda k: (mapping[k] or {}).get("parent"),
                       lambda k: (mapping[k] or {}).get("children") or [], conv.get("current_node"))
    turns = []
    for k in ids:
        m = (mapping[k] or {}).get("message")
        if not m:
            continue
        when = _iso(m.get("inserted_at") or m.get("create_time"))[1]
        for f in m.get("fragments") or []:
            if not isinstance(f, dict):
                continue
            kind = str(f.get("type", "")).upper()
            role = "user" if kind == "REQUEST" else "assistant" if kind == "RESPONSE" else None
            text = str(f.get("content") or f.get("text") or "").strip()
            if not role or not text:
                continue
            if turns and turns[-1][0] == role and turns[-1][1] == when:
                turns[-1] = (role, when, turns[-1][2] + "\n\n" + text)
            else:
                turns.append((role, when, text))
    return turns


def _grok_time(t):
    """BSON {"$date": {"$numberLong": ms}} or {"$date": iso}, an ISO string, or epoch."""
    if isinstance(t, dict):
        d = t.get("$date", t)
        if isinstance(d, dict):
            d = d.get("$numberLong")
            try:
                return _iso(int(d) / 1000.0)
            except (TypeError, ValueError):
                return "", ""
        return _iso(d)
    if isinstance(t, (int, float)) and t > 1e11:
        return _iso(t / 1000.0)
    return _iso(t)


def grok_turns(conv):
    """responses: [{response: {_id, parent_response_id, sender, message, create_time}}].
    The kept branch ends at the newest leaf; sender 'human' is the person, anything else
    (assistant, ASSISTANT, a model name) the answer."""
    rs = [r.get("response", r) for r in conv.get("responses") or [] if isinstance(r, dict)]
    rs = [r for r in rs if isinstance(r, dict)]
    if all(r.get("_id") for r in rs):
        nodes = {r["_id"]: r for r in rs}
        kids = {}
        for r in rs:
            kids.setdefault(r.get("parent_response_id"), []).append(r["_id"])
        leaves = [k for k in nodes if k not in kids]
        newest = max(leaves, key=lambda k: _grok_time(nodes[k].get("create_time"))[1], default=None)
        rs = [nodes[k] for k in _main_branch(nodes, lambda k: nodes[k].get("parent_response_id"),
                                             lambda k: kids.get(k, []), newest)]
    else:
        rs.sort(key=lambda r: _grok_time(r.get("create_time"))[1])
    turns = []
    for r in rs:
        text = str(r.get("message") or "").strip()
        if text:
            role = "user" if str(r.get("sender", "")).lower() == "human" else "assistant"
            turns.append((role, _grok_time(r.get("create_time"))[1], text))
    return turns


def lechat_turns(conv):
    turns = []
    for m in conv.get("chat_messages") or conv.get("messages") or []:
        if not isinstance(m, dict):
            continue
        c = m.get("content")
        text = c if isinstance(c, str) else "\n".join(
            b.get("text", "") for b in (c or []) if isinstance(b, dict) and b.get("type", "text") == "text")
        role = "user" if str(m.get("role", "")).lower() in ("user", "human") else "assistant"
        if text.strip():
            turns.append((role, _iso(m.get("created_at") or m.get("timestamp"))[1], text.strip()))
    return turns


def _copilot_time(s):
    s = (s or "").strip()
    if not s:
        return ""
    got = _iso(s)[1]
    if got:
        return got
    for fmt in ("%m/%d/%Y %H:%M:%S %z", "%m/%d/%Y %I:%M:%S %p %z", "%m/%d/%Y %H:%M:%S", "%m/%d/%Y %I:%M:%S %p"):
        try:
            d = dt.datetime.strptime(s, fmt)
            if d.tzinfo is None:
                d = d.replace(tzinfo=dt.timezone.utc)
            return d.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            continue
    return ""


def copilot_conversations(raw):
    """A Copilot privacy-dashboard CSV. Rows carry no conversation id: rows are grouped by
    the Conversation / ChatName column; rows without one (the Windows apps file, prompts
    only) start a new conversation after GAP_S of quiet."""
    text = raw.decode("utf-8-sig", "replace") if isinstance(raw, bytes) else raw
    reader = csv.DictReader(io.StringIO(text))
    cols = {re.sub(r"[^a-z]", "", (c or "").lower()): c for c in reader.fieldnames or []}
    msg_col = cols.get("message") or cols.get("messagecontent") or cols.get("prompt")
    time_col = cols.get("time") or cols.get("createdat") or cols.get("timestamp")
    if not msg_col or not time_col:
        return []
    name_col, author_col = cols.get("conversation") or cols.get("chatname"), cols.get("author")
    rows = []
    for r in reader:
        msg = (r.get(msg_col) or "").strip()
        if not msg:
            continue
        who = (r.get(author_col) or "").strip().lower() if author_col else "human"
        role = "user" if who in ("human", "user", "you", "me") else "assistant"
        rows.append(((r.get(name_col) or "").strip() if name_col else "", _copilot_time(r.get(time_col)), role, msg))
    rows.sort(key=lambda x: x[1])
    groups, named, last_t = [], {}, None
    for name, when, role, msg in rows:
        if name:
            if name not in named:
                named[name] = (name, [])
                groups.append(named[name])
            named[name][1].append((role, when, msg))
            continue
        t = dt.datetime.fromisoformat(when.replace("Z", "+00:00")).timestamp() if when else None
        if last_t is None or t is None or t - last_t > GAP_S or not groups or groups[-1][0]:
            groups.append(("", []))
        groups[-1][1].append((role, when, msg))
        last_t = t
    out = []
    for name, turns in groups:
        first = next((m for r, _, m in turns if r == "user"), turns[0][2])
        title = name or _one_line(first)[:80]
        cid = "copilot-" + hashlib.sha256(f"{title}\n{turns[0][1]}".encode()).hexdigest()[:12]
        out.append({"_norm": {"id": cid, "source": "copilot", "date": turns[0][1][:10],
                              "updated": turns[-1][1], "title": title, "turns": turns}})
    return out


def normalize(conv):
    """One conversation from any export -> dict(id, source, date, updated, title, turns)."""
    if "_norm" in conv:  # Gemini and Copilot arrive grouped already
        return conv["_norm"]
    if "mapping" in conv:
        mp = conv.get("mapping") or {}
        if any(isinstance(v, dict) and isinstance(v.get("message"), dict) and "fragments" in v["message"]
               for v in mp.values()):
            return {"id": conv.get("id") or "", "source": "deepseek",
                    "date": _iso(conv.get("inserted_at") or conv.get("create_time"))[0],
                    "updated": _iso(conv.get("updated_at") or conv.get("update_time"))[1],
                    "title": conv.get("title") or "", "turns": deepseek_turns(conv)}
        return {"id": conv.get("conversation_id") or conv.get("id") or "", "source": "chatgpt",
                "date": _iso(conv.get("create_time"))[0], "updated": _iso(conv.get("update_time"))[1],
                "title": conv.get("title") or "", "turns": chatgpt_turns(conv)}
    msgs = conv.get("chat_messages")
    if isinstance(msgs, list) and not (msgs and all(isinstance(m, dict) and "sender" not in m and "role" in m
                                                    for m in msgs)):
        return {"id": conv.get("uuid") or "", "source": "claude",
                "date": _iso(conv.get("created_at"))[0], "updated": _iso(conv.get("updated_at"))[1],
                "title": conv.get("name") or "", "turns": claude_turns(conv)}
    if isinstance(conv.get("conversation"), dict) and isinstance(conv.get("responses"), list):
        c = conv["conversation"]
        return {"id": c.get("id") or "", "source": "grok", "date": _grok_time(c.get("create_time"))[0],
                "updated": _grok_time(c.get("modify_time"))[1], "title": c.get("title") or "",
                "turns": grok_turns(conv)}
    msgs = msgs if isinstance(msgs, list) else conv.get("messages")
    if isinstance(msgs, list) and msgs and all(isinstance(m, dict) and "role" in m and "sender" not in m for m in msgs):
        return {"id": conv.get("id") or conv.get("uuid") or "", "source": "lechat",
                "date": _iso(conv.get("created_at"))[0], "updated": _iso(conv.get("updated_at"))[1],
                "title": conv.get("title") or conv.get("name") or "", "turns": lechat_turns(conv)}
    return None


# ── the fallback: one pasted or dropped conversation ─────────────────────

_USER = r"you|user|me|human|я|вы|пользователь"
_AI = (r"chatgpt|assistant|ai|gemini|claude|copilot|grok|deepseek|perplexity|le chat|mistral|bot|model|"
       r"ассистент|ии")
_MARK = re.compile(r"^\s*(?:#{1,6}\s*)?(?:\*\*|__)?(" + _USER + "|" + _AI + r")(?:\s+said)?(?:\*\*|__)?\s*:(?:\*\*|__)?\s*(.*)$",
                   re.IGNORECASE)
_VENDOR = {"chatgpt": "chatgpt", "gemini": "gemini", "claude": "claude", "copilot": "copilot", "grok": "grok",
           "deepseek": "deepseek", "perplexity": "perplexity", "le chat": "lechat", "mistral": "lechat"}


def pasted_turns(text):
    """Turns from 'You:' / 'ChatGPT:' style markers (also 'You said:', '**User:**', '## Me:');
    without both a person and an AI marker, one 'Me' block holding everything.
    Returns (turns, vendor named by the AI markers or '')."""
    turns, vendors, cur = [], set(), None
    for line in text.splitlines():
        m = _MARK.match(line)
        if m:
            who = m.group(1).lower()
            role = "user" if re.fullmatch(_USER, who) else "assistant"
            if role == "assistant" and who in _VENDOR:
                vendors.add(_VENDOR[who])
            cur = [role, [m.group(2)] if m.group(2).strip() else []]
            turns.append(cur)
        elif cur is not None:
            cur[1].append(line)
        elif line.strip():
            cur = ["user", [line]]
            turns.append(cur)
    roles = {r for r, _ in turns}
    if roles != {"user", "assistant"}:
        return [("user", "", text.strip())], ""
    out = [(r, "", "\n".join(ls).strip()) for r, ls in turns if "\n".join(ls).strip()]
    return out, (vendors.pop() if len(vendors) == 1 else "")


def _vendor_named(text):
    head = text[:3000].lower()
    for needle, v in (("perplexity", "perplexity"), ("chat.mistral.ai", "lechat"), ("le chat", "lechat"),
                      ("gemini.google.com", "gemini"), ("chatgpt.com", "chatgpt"), ("claude.ai", "claude"),
                      ("copilot.microsoft.com", "copilot"), ("grok.com", "grok"), ("chat.deepseek.com", "deepseek")):
        if needle in head:
            return v
    return ""


def file_text(name, data):
    """(text, title) of a dropped file: pdf through pypdf, html stripped, else utf-8 text.
    Raises ValueError when it is not text."""
    low = (name or "").lower()
    if low.endswith(".pdf") or data[:5] == b"%PDF-":
        try:
            from pypdf import PdfReader
        except ImportError as e:
            raise ValueError("pdf needs pypdf") from e
        reader = PdfReader(io.BytesIO(data))
        text = "\n\n".join((p.extract_text() or "") for p in reader.pages).strip()
        title = ""
        try:
            title = str((reader.metadata or {}).get("/Title") or "")
        except Exception:
            pass
        return text, title
    try:
        s = data.decode("utf-16") if data[:2] in (b"\xff\xfe", b"\xfe\xff") else data.decode("utf-8-sig")
    except UnicodeDecodeError as e:
        raise ValueError("not text") from e
    if "\x00" in s:
        raise ValueError("not text")
    if low.endswith((".html", ".htm")) or re.match(r"\s*(<!doctype html|<html)", s[:200], re.IGNORECASE):
        return html_text(s)
    return s, ""


def pasted_conversation(text, title=None, today=None):
    """One normalized conversation from pasted text."""
    text = text.replace("\r\n", "\n").strip()
    turns, vendor = pasted_turns(text)
    source = vendor or _vendor_named(text) or "pasted"
    if not title:
        first = next((l for l in text.splitlines() if l.strip()), "")
        m = _MARK.match(first)
        title = _one_line(m.group(2) if m else first).lstrip("# ")[:80] or "Pasted conversation"
    date = today or dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    return {"id": "pasted-" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:12], "source": source,
            "date": date, "updated": "", "title": _one_line(title), "turns": turns}


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
        label = ROLE_LABEL[role] + (" (" + DISPLAY.get(c["source"], c["source"].capitalize()) + ")"
                                    if role == "assistant" else "")
        body += [f"## {label}" + (f", {when}" if when else ""), "", text, ""]
    return "\n".join(head + body)


def _load_or_paste(src, title=None):
    """An export file, else (a bare text, markdown, html or pdf file) one pasted conversation."""
    p = pathlib.Path(src).expanduser()
    if p.is_file() and not zipfile.is_zipfile(p) and not p.name.lower().endswith(".json"):
        data = p.read_bytes()
        convs = []
        if p.name.lower().endswith(".csv"):
            convs = copilot_conversations(data)
        elif p.name.lower().endswith((".html", ".htm")):
            convs = gemini_html_conversations(data)
        if convs:
            return convs, []
        text, html_title = file_text(p.name, data)
        if not text.strip():
            return [], []
        return [{"_norm": pasted_conversation(text, title or html_title)}], []
    return load_export(p)


def prep(src, out_dir, title=None):
    out = pathlib.Path(out_dir)
    (out / "docs").mkdir(parents=True, exist_ok=True)
    convs, projects = _load_or_paste(src, title)
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
                           files={"file": (name, data, content_type(name))}, timeout=120)
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


def content_type(name):
    """pdf and docx are extracted by the api from their type; everything else is read as text."""
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    return {"pdf": "application/pdf",
            "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}.get(ext, "text/markdown")


def doc_name(row):
    """The document's name in memory: the manifest's name column (sort_inbox.py writes
    <area>/<file>, which retrieval pins), else the file's own name."""
    return row.get("name") or row["file"].rsplit("/", 1)[-1]


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
            res = brain.propose(permit, doc_name(r), data, layer)
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
