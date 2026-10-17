#!/usr/bin/env python3
"""Sort one inbox folder into the brain's areas, through the gate (docs/IMPORT.md §7).

  sort     <inbox> <out_dir> [--llm] [--owner NAME] [--brain-name NAME]
           walks the inbox (never follows links, never runs anything), hands
           ChatGPT/Claude exports to import_chats.py prep, skips exact
           duplicates by sha256, and files a copy of every other file under
           out_dir/<area>/: identity, projects, writing, thinking (the folders
           retrieval pins), library (kept as a file, not remembered) or
           outside (looks like private papers; not copied, never offered).
           Writes sorted.tsv (every file, with a reason), manifest.tsv (what
           would be remembered, with its manifest id), summary.txt and
           persona_draft.md.
  manifest <out_dir>
           after the person edits the area column of sorted.tsv: moves the
           filed copies and writes manifest.tsv again (a new id)
  persona  <out_dir> [--owner NAME] [--brain-name NAME]
           writes persona_draft.md again from what is filed now
  persona-approve <out_dir> --api URL --yes <draft_id>
           the person's yes for the draft as it is on disk now; writes it
           through PUT /persona, the Persona page's own save

Nothing is remembered here. The memory rows go through import_chats.py
propose and approve, unchanged: one permit, one proposal per document, one yes
for the named manifest id. Rules decide first (names, extensions, headings);
--llm asks the brain's own model through POST /chat/completions only about
text files no rule placed. BRAIN_API_KEY comes from the environment.
"""
import argparse
import collections
import datetime as dt
import hashlib
import html
import importlib.util
import json
import os
import pathlib
import re
import shutil
import sys
import zipfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("import_chats", ROOT / "scripts" / "import_chats.py")
ic = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ic)

MEMORY_AREAS = ("identity", "projects", "writing", "thinking")  # api/main.py RAG_TIER1..2C defaults
AREAS = MEMORY_AREAS + ("library", "outside")
SORTED_COLS = ["file", "source", "sha256", "area", "reason", "size", "kind"]
MANIFEST_COLS = ["id", "file", "name", "sha256", "area", "reason", "size", "kind"]

TEXT_EXT = {".txt", ".md", ".markdown", ".rst", ".org", ".text"}
DOC_EXT = {".pdf", ".docx"}
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".gif", ".heic", ".webp", ".tif", ".tiff", ".bmp", ".svg"}
AUDIO_EXT = {".mp3", ".m4a", ".wav", ".aac", ".flac", ".ogg", ".opus", ".aiff", ".aif"}
VIDEO_EXT = {".mp4", ".mov", ".mkv", ".avi", ".webm"}
DATA_EXT = {".csv", ".tsv", ".xlsx", ".xls", ".numbers", ".json", ".xml", ".zip", ".tar", ".gz"}
SECRET_EXT = {".kdbx", ".pem", ".key", ".p12", ".pfx", ".ovpn", ".gpg", ".asc", ".env"}
IGNORED = {".ds_store", "thumbs.db", "desktop.ini", ".localized"}

# Name words per area. A word matches a whole token of the file name.
NAME_RULES = {
    "outside": ["password", "passwords", "passport", "ssn", "bank", "statement", "statements", "tax",
                "taxes", "payslip", "salary", "medical", "diagnosis", "prescription", "insurance",
                "credentials", "secret", "secrets", "id_rsa", "seed", "recovery", "license"],
    "identity": ["about", "bio", "biography", "cv", "resume", "profile", "me", "identity", "values",
                 "principles", "manifesto", "intro", "introduction", "whoami", "portfolio", "personal"],
    "projects": ["project", "projects", "roadmap", "spec", "specs", "plan", "proposal", "brief", "readme",
                 "todo", "backlog", "design", "requirements", "pitch", "prd", "milestones", "launch", "deck"],
    "writing": ["essay", "essays", "post", "posts", "article", "articles", "draft", "drafts", "chapter",
                "poem", "poems", "story", "stories", "blog", "newsletter", "manuscript", "lyrics",
                "script", "speech", "talk", "column", "review", "letter"],
    "thinking": ["notes", "note", "journal", "diary", "thoughts", "thought", "idea", "ideas", "reflection",
                 "reflections", "musings", "memo", "daily", "weekly", "log", "brainstorm", "questions"],
}
# Heading or first-line phrases per area (lower case, matched inside the line).
HEAD_RULES = {
    "identity": ["about me", "who i am", "curriculum vitae", "my values", "bio", "experience", "education"],
    "projects": ["goals", "milestones", "scope", "roadmap", "requirements", "deliverables", "timeline", "status"],
    "writing": ["chapter", "introduction", "conclusion", "epilogue", "prologue", "abstract"],
    "thinking": ["notes", "journal", "today", "dear diary", "reflection", "open questions", "ideas"],
}
DATED = re.compile(r"(19|20)\d\d[-_.]?[01]\d[-_.]?[0-3]\d")


# ── reading a file without running it ─────────────────────────────────────

def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def excerpt(p, limit=4000):
    """First text of a text, md, docx or pdf file; '' for anything else."""
    ext = p.suffix.lower()
    try:
        if ext in TEXT_EXT:
            with open(p, "rb") as f:
                return f.read(limit).decode("utf-8", errors="replace")
        if ext == ".docx" and zipfile.is_zipfile(p):
            with zipfile.ZipFile(p) as z:
                xml = z.read("word/document.xml").decode("utf-8", errors="replace")
            paras = re.findall(r"<w:p[ >].*?</w:p>", xml, flags=re.DOTALL)
            lines = [html.unescape("".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", x))) for x in paras]
            return "\n".join(l for l in lines if l.strip())[:limit]
        if ext == ".pdf":
            try:
                import pypdf  # optional; without it a pdf is sorted by name and title only
                r = pypdf.PdfReader(str(p))
                return "\n".join((pg.extract_text() or "") for pg in r.pages[:2])[:limit]
            except Exception:
                with open(p, "rb") as f:
                    m = re.search(rb"/Title\s*\(([^)]{1,200})\)", f.read(200000))
                return m.group(1).decode("latin-1") if m else ""
    except (OSError, KeyError, zipfile.BadZipFile):
        return ""
    return ""


def _tokens(name):
    return set(t for t in re.split(r"[^a-z0-9]+", name.lower()) if t) | {name.lower().rsplit(".", 1)[0]}


def _head_lines(text, n=12):
    out = []
    for line in text.splitlines():
        s = line.strip()
        if s:
            out.append(s)
        if len(out) >= n:
            break
    return out


def classify(path, text):
    """Rules only. Returns (area, reason, kind); area None means no rule placed it."""
    name, ext = path.name, path.suffix.lower()
    toks = _tokens(name)
    if ext in SECRET_EXT or name.lower().startswith("id_rsa"):
        return "outside", f"key or secret file type ({ext or name})", "secret"
    hit = [w for w in NAME_RULES["outside"] if w in toks]
    if hit:
        return "outside", f"name has '{hit[0]}': private papers stay outside", "private"
    if ext in IMAGE_EXT:
        return "library", f"image ({ext}); sorted by name only, kept as a file", "image"
    if ext in AUDIO_EXT or ext in VIDEO_EXT:
        return "library", f"{'audio' if ext in AUDIO_EXT else 'video'} ({ext}); kept as a file", "media"
    if ext not in TEXT_EXT | DOC_EXT:
        return "library", f"{ext or 'no extension'} is not a text document; kept as a file", "file"
    kind = ext.lstrip(".")
    if not text.strip() and ext in TEXT_EXT:
        return "library", "empty text", kind
    score = collections.Counter()
    why = {}
    for area in MEMORY_AREAS:
        for w in NAME_RULES[area]:
            if w in toks:
                score[area] += 2
                why.setdefault(area, f"name has '{w}'")
    for line in _head_lines(text):
        low = line.lstrip("#*= ").lower()
        is_head = line.startswith("#") or len(line) < 60
        if not is_head:
            continue
        for area, phrases in HEAD_RULES.items():
            for ph in phrases:
                if low.startswith(ph):
                    score[area] += 1
                    why.setdefault(area, f"heading '{line[:50]}'")
    if not score and DATED.search(name):
        return "thinking", "dated name, reads as a journal or note", kind
    if not score and ext in TEXT_EXT and len(text) < 4000 and len(_head_lines(text, 99)) <= 40 \
            and sum(1 for l in _head_lines(text, 99) if l.startswith(("-", "*", "•"))) >= 3:
        return "thinking", "short list of points, reads as notes", kind
    if not score:
        return None, "no rule matched", kind
    best = max(MEMORY_AREAS, key=lambda a: (score[a], -MEMORY_AREAS.index(a)))
    return best, why[best], kind


# ── exports: handed to import_chats.py prep ───────────────────────────────

def _is_conversations_json(p):
    if not re.fullmatch(r"conversations(-\d+)?\.json", p.name):
        return False
    try:
        with open(p, "rb") as f:
            head = f.read(65536).decode("utf-8", errors="replace")
    except OSError:
        return False
    return '"mapping"' in head or '"chat_messages"' in head


def is_export_zip(p):
    if p.suffix.lower() != ".zip" or not zipfile.is_zipfile(p):
        return False
    with zipfile.ZipFile(p) as z:
        return any(re.fullmatch(r"conversations(-\d+)?\.json", n.rsplit("/", 1)[-1]) for n in z.namelist())


# ── the brain's own model, only when asked (--llm) ────────────────────────

def brain_llm(api, key, nodeos=None, brain_id=None, nodeos_key=None):
    """Return ask(name, text) -> (area, reason) | None, through POST /chat/completions."""
    import requests
    nodeos = nodeos or os.getenv("NODEOS_URL", "http://127.0.0.1:8001")
    brain_id = brain_id or os.getenv("BRAIN_ID", "my-brain-01")
    nh = {"X-Internal-Key": nodeos_key or os.getenv("NODEOS_INTERNAL_KEY", "")}
    h = {"X-Api-Key": key} if key else {}

    def ask(name, text):
        r = requests.post(f"{nodeos}/v1/loops/request", headers=nh, timeout=5, json={
            "node_id": brain_id, "agent_id": "script/sort_inbox", "loop_type": "research",
            "ttl_seconds": 120, "reason": "inbox sorter: one file, area only"})
        r.raise_for_status()
        p = r.json()
        prompt = (f"Sort one file of the owner into exactly one area: identity (who they are), projects "
                  f"(things they build or plan), writing (finished or drafted pieces), thinking (notes, "
                  f"journals, ideas) or library (reference, not theirs). Answer only JSON "
                  f'{{"area": "...", "reason": "under 12 words"}}.\n\nFile name: {name}\n\n{text[:1500]}')
        r = requests.post(f"{api.rstrip('/')}/chat/completions", headers=h, timeout=60, json={
            "messages": [{"role": "user", "content": prompt}], "stream": False,
            "permit_id": p["permit_id"], "permit_token": p["permit_token"]})
        r.raise_for_status()
        return parse_llm_answer(r.json())
    return ask


def parse_llm_answer(body):
    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return None
    m = re.search(r"\{.*\}", content or "", flags=re.DOTALL)
    try:
        d = json.loads(m.group(0)) if m else {}
    except ValueError:
        d = {}
    area = str(d.get("area") or (content or "").strip().split(" ")[0]).strip().lower().strip(".,\"'")
    if area not in MEMORY_AREAS + ("library",):
        return None
    return area, ic._one_line(d.get("reason") or "the brain's model")[:80]


# ── sort ──────────────────────────────────────────────────────────────────

def _place(out, area, src, sha):
    """Copy src to out/<area>/<name>; a different file of the same name gets the hash in its name."""
    dest_dir = out / area
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name
    if dest.exists() and sha256_file(dest) != sha:
        dest = dest_dir / f"{src.stem}_{sha[:8]}{src.suffix}"
    shutil.copy2(src, dest)
    return dest.relative_to(out).as_posix()


def walk(inbox):
    """Files under inbox, sorted; symlinks are listed, never followed."""
    for dirpath, dirnames, filenames in os.walk(inbox, followlinks=False):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith(".") and d != "__MACOSX")
        for f in sorted(filenames):
            yield pathlib.Path(dirpath) / f


def sort_inbox(inbox, out_dir, llm=None, log=print):
    inbox, out = pathlib.Path(inbox).resolve(), pathlib.Path(out_dir).resolve()
    if not inbox.is_dir():
        raise SystemExit(f"not a folder: {inbox}")
    if out == inbox or inbox in out.parents:
        raise SystemExit("out_dir must be outside the inbox")
    out.mkdir(parents=True, exist_ok=True)
    rows, seen, exports, done_dirs = [], {}, [], set()
    export_dirs = {p.parent for p in walk(inbox) if not p.is_symlink() and _is_conversations_json(p)}
    for p in walk(inbox):
        rel = p.relative_to(inbox).as_posix()
        if p.name.lower() in IGNORED or p.name.startswith("._"):
            continue
        if p.is_symlink():
            rows.append({"file": "", "source": rel, "sha256": "", "area": "skipped",
                         "reason": "a link; links are not followed", "size": 0, "kind": "link"})
            continue
        exp_dir = next((d for d in export_dirs if d == p.parent or d in p.parents), None)
        if exp_dir is not None:
            if exp_dir in done_dirs:
                continue
            done_dirs.add(exp_dir)
            dest = out / "chats" / ic._slug(exp_dir.relative_to(inbox).as_posix() or exp_dir.name)
            n = len(ic.prep(exp_dir, dest))
            exports.append((exp_dir.relative_to(inbox).as_posix() or ".", dest, n))
            rows.append({"file": dest.relative_to(out).as_posix(), "source": exp_dir.relative_to(inbox).as_posix() or ".",
                         "sha256": "", "area": "chat-export", "reason": f"ChatGPT/Claude export folder, {n} documents prepared",
                         "size": sum(f.stat().st_size for f in exp_dir.rglob("*") if f.is_file()), "kind": "export"})
            continue
        sha, size = sha256_file(p), p.stat().st_size
        if sha in seen:
            rows.append({"file": "", "source": rel, "sha256": sha, "area": "duplicate",
                         "reason": f"same bytes as {seen[sha]}", "size": size, "kind": p.suffix.lower().lstrip(".")})
            continue
        seen[sha] = rel
        if is_export_zip(p):
            dest = out / "chats" / ic._slug(p.stem)
            n = len(ic.prep(p, dest))
            exports.append((rel, dest, n))
            rows.append({"file": dest.relative_to(out).as_posix(), "source": rel, "sha256": sha, "area": "chat-export",
                         "reason": f"ChatGPT/Claude export, {n} documents prepared", "size": size, "kind": "export"})
            continue
        text = excerpt(p)
        area, reason, kind = classify(p, text)
        if area is None and llm and text.strip():
            try:
                got = llm(p.name, text)
            except Exception as e:  # the model is a helper; rules stand without it
                got, reason = None, f"no rule matched; the brain's model failed ({type(e).__name__})"
            if got:
                area, reason = got[0], f"the brain's model: {got[1]}"
        if area is None:
            area, reason = "library", f"{reason}; kept as a file until you move it"
        row = {"file": "", "source": rel, "sha256": sha, "area": area, "reason": reason, "size": size, "kind": kind}
        if area != "outside":
            row["file"] = _place(out, area, p, sha)
        rows.append(row)
    ic.write_tsv(out / "sorted.tsv", SORTED_COLS, rows,
                 comments=[f"sorted: {dt.date.today().isoformat()} from {inbox.name}",
                           "edit the area column, then: sort_inbox.py manifest <out_dir>"])
    mid, mrows = write_manifest(out, rows)
    summary = summarize(rows, exports, mid, mrows, out)
    (out / "summary.txt").write_text(summary + "\n", encoding="utf-8")
    log(summary)
    return rows


def write_manifest(out, rows):
    """manifest.tsv in the shape import_chats.py propose/approve read: id, file, sha256,
    plus name (the document name in memory, <area>/<file>, which retrieval pins)."""
    mrows = []
    for r in rows:
        if r["area"] in MEMORY_AREAS and r["file"]:
            mrows.append({"id": r["sha256"][:16], "file": r["file"], "name": r["file"], "sha256": r["sha256"],
                          "area": r["area"], "reason": r["reason"], "size": r["size"], "kind": r["kind"]})
    mid = ic.manifest_id(mrows)
    ic.write_tsv(out / "manifest.tsv", MANIFEST_COLS, mrows,
                 comments=[f"manifest_id: {mid}", f"selected: {dt.date.today().isoformat()}", "from: sort_inbox.py"])
    return mid, mrows


def summarize(rows, exports, mid, mrows, out):
    c = collections.Counter(r["area"] for r in rows)
    files = sum(v for k, v in c.items() if k not in ("chat-export", "skipped"))
    parts = [f"{c[a]} {a}" for a in AREAS if c[a]]
    lines = [f"{files} files: " + (", ".join(parts) or "nothing to sort")
             + (f"; {c['duplicate']} duplicate{'s' if c['duplicate'] > 1 else ''} skipped" if c["duplicate"] else "")
             + (f"; {c['skipped']} links skipped" if c["skipped"] else "")
             + (f"; {c['chat-export']} chat export{'s' if c['chat-export'] > 1 else ''}" if c["chat-export"] else "")]
    for src, dest, n in exports:
        lines.append(f"chat export {src}: {n} documents in {dest}; choose with "
                     f"import_chats.py select {dest} --newest 50")
    if c["outside"]:
        lines.append(f"{c['outside']} files look private (keys, bank, health, IDs): not copied, never offered")
    if mrows:
        lines.append(f"to remember: {len(mrows)} documents, manifest id {mid}")
        lines.append(f"next: import_chats.py propose {out}  then, with the person's yes: "
                     f"import_chats.py approve {out} --yes {mid}")
    else:
        lines.append("nothing to remember yet")
    return "\n".join(lines)


def remanifest(out_dir, log=print):
    """Apply the person's edits to the area column of sorted.tsv: move filed copies, new manifest."""
    out = pathlib.Path(out_dir)
    rows = ic.read_tsv(out / "sorted.tsv")
    for r in rows:
        if r["area"] not in AREAS or not r["file"] or r["kind"] == "export":
            continue
        cur = out / r["file"]
        if r["area"] == "outside":
            if cur.exists():
                cur.unlink()
            r["file"] = ""
            continue
        if r["file"].split("/", 1)[0] != r["area"]:
            dest_dir = out / r["area"]
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / cur.name
            if dest.exists():
                dest = dest_dir / f"{cur.stem}_{r['sha256'][:8]}{cur.suffix}"
            shutil.move(str(cur), dest)
            r["file"] = dest.relative_to(out).as_posix()
            r["reason"] = "moved by the owner"
    ic.write_tsv(out / "sorted.tsv", SORTED_COLS, rows,
                 comments=[f"edited: {dt.date.today().isoformat()}",
                           "edit the area column, then: sort_inbox.py manifest <out_dir>"])
    mid, mrows = write_manifest(out, rows)
    log(f"manifest: {len(mrows)} documents, id {mid}")
    return mid


# ── persona draft ─────────────────────────────────────────────────────────

DRAFT_BANNER = ("# DRAFT persona, written by the inbox sorter from your identity and writing files.\n"
                "# Nothing here is live. Read every line, change what is wrong, then approve it:\n"
                "#   sort_inbox.py persona-approve <out_dir> --yes <draft_id>\n")


def _body_lines(text):
    for line in text.splitlines():
        s = line.strip().lstrip("-*• ").strip()
        if s and not line.lstrip().startswith(("#", "|", "```")) and len(s) > 3:
            yield s


def _title(path, text):
    for line in text.splitlines():
        if line.startswith("#"):
            return line.lstrip("# ").strip()
    return path.stem.replace("_", " ").replace("-", " ")


def _style(texts):
    words = " ".join(texts).split()
    sentences = [s for s in re.split(r"[.!?]+\s", " ".join(texts)) if s.strip()]
    if not words or not sentences:
        return []
    avg = len(words) / len(sentences)
    first = sum(1 for w in words if w in ("I", "I'm", "I've", "my", "My", "me")) / len(words)
    out = [f"- Their sentences average about {avg:.0f} words; match that length."]
    if first > 0.02:
        out.append("- They write in the first person, plainly.")
    return out


def persona_draft(out_dir, owner=None, brain_name=None):
    """persona_draft.md in the shape of api/brain_persona.template.md, plus what the files say."""
    sys.path.insert(0, str(ROOT))
    from api.persona_tools import personalize_text
    out = pathlib.Path(out_dir)
    template = (ROOT / "api" / "brain_persona.template.md").read_text(encoding="utf-8")
    ident, writing, projects = [], [], []
    for area, bucket in (("identity", ident), ("writing", writing), ("projects", projects)):
        for p in sorted((out / area).glob("*")) if (out / area).is_dir() else []:
            bucket.append((p, excerpt(p)))
    if not owner:
        for _, t in ident:
            m = re.search(r"^\s*(?:name|my name is)\s*[:\-]?\s*([A-Z][\w'\-]+(?: [A-Z][\w'\-]+){0,2})", t,
                          flags=re.MULTILINE | re.IGNORECASE)
            if m:
                owner = m.group(1).strip()
                break
    owner_s, brain_s = owner or "[OWNER_NAME]", brain_name or "[BRAIN_NAME]"
    base = personalize_text(template, brain_s, owner_s)
    about = [f"About {owner_s} (drafted from their files; every line names its source):"]
    for p, t in ident:
        for s in list(_body_lines(t))[:4]:
            about.append(f"- {s[:200]} ({p.parent.name}/{p.name})")
    if projects:
        about.append("Their projects:")
        about += [f"- {_title(p, t)[:100]} ({p.parent.name}/{p.name})" for p, t in projects[:10]]
    if writing:
        about.append("Their writing:")
        about += [f"- {_title(p, t)[:100]} ({p.parent.name}/{p.name})" for p, t in writing[:6]]
        about += _style([t for _, t in writing])
    if len(about) == 1:
        about.append("- (no identity or writing files were found; write this part yourself)")
    block = "\n".join(about) + "\n\n"
    text = base.replace("Identity:\n", block + "Identity:\n", 1) if "Identity:\n" in base else base + "\n" + block
    draft = DRAFT_BANNER + "\n" + text.lstrip("\n")
    (out / "persona_draft.md").write_text(draft, encoding="utf-8")
    return draft_id(draft)


def draft_id(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def strip_draft(text):
    lines = text.split("\n")
    i = 0
    while i < len(lines) and (lines[i].startswith("# DRAFT") or lines[i].startswith("#  ")
                              or lines[i].startswith("# Nothing here is live")):
        i += 1
    while i < len(lines) and not lines[i].strip():
        i += 1
    return "\n".join(lines[i:])


def persona_approve(out_dir, yes, put, log=print):
    """The person's yes for persona_draft.md as it is now; put(text) is PUT /persona."""
    out = pathlib.Path(out_dir)
    text = (out / "persona_draft.md").read_text(encoding="utf-8")
    did = draft_id(text)
    if yes != did:
        raise SystemExit(f"--yes {yes} does not name this draft (its id is {did}); nothing written")
    persona = strip_draft(text)
    if not persona.strip():
        raise SystemExit("the draft is empty; nothing written")
    put(persona)
    record = {"draft_id": did, "approved_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
              "chars": len(persona), "placeholders_left": [t for t in ("[BRAIN_NAME]", "[OWNER_NAME]") if t in persona]}
    (out / "persona_approval.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    log(f"persona written through PUT /persona ({len(persona)} chars, draft {did})")
    return record


def put_persona(api, key):
    import requests

    def put(text):
        r = requests.put(f"{api.rstrip('/')}/persona", json={"persona": text},
                         headers={"X-Api-Key": key} if key else {}, timeout=15)
        r.raise_for_status()
        return r.json()
    return put


# ── command line ──────────────────────────────────────────────────────────

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("sort"); p.add_argument("inbox"); p.add_argument("out_dir")
    p.add_argument("--llm", action="store_true", help="ask the brain's model about files no rule placed")
    p = sub.add_parser("manifest"); p.add_argument("out_dir")
    p = sub.add_parser("persona"); p.add_argument("out_dir")
    p = sub.add_parser("persona-approve"); p.add_argument("out_dir")
    p.add_argument("--yes", required=True, help="the draft id printed by sort or persona")
    for name in ("sort", "persona"):
        sub.choices[name].add_argument("--owner"); sub.choices[name].add_argument("--brain-name")
    for name in ("sort", "persona-approve"):
        sub.choices[name].add_argument("--api", default=os.getenv("API_BASE", "http://localhost:8010"))
    a = ap.parse_args(argv)
    key = os.getenv("BRAIN_API_KEY", "")
    if a.cmd == "sort":
        sort_inbox(a.inbox, a.out_dir, llm=brain_llm(a.api, key) if a.llm else None)
    elif a.cmd == "manifest":
        remanifest(a.out_dir)
        return
    elif a.cmd == "persona-approve":
        print(json.dumps(persona_approve(a.out_dir, a.yes, put_persona(a.api, key)), indent=2))
        return
    did = persona_draft(a.out_dir, owner=a.owner, brain_name=a.brain_name)
    print(f"persona draft: {pathlib.Path(a.out_dir) / 'persona_draft.md'}  id {did}")
    print(f"after reading it: sort_inbox.py persona-approve {a.out_dir} --yes {did}")


if __name__ == "__main__":
    main()
