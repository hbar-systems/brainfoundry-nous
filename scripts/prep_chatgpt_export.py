import sys, json, pathlib
from bs4 import BeautifulSoup

src = pathlib.Path(sys.argv[1]).expanduser().resolve()
out = pathlib.Path(sys.argv[2] if len(sys.argv)>2 else "prepared_docs").resolve()
out.mkdir(parents=True, exist_ok=True)

def write_txt(name, text):
    t = " ".join(str(text).split())
    p = out / f"{name}.txt"
    if t:
        p.write_text(t[:200000], encoding="utf-8")
        print(f"Wrote: {p.name} ({len(t)} chars)")

def parts_to_text(parts):
    out = []
    for p in (parts or []):
        if isinstance(p, str):
            out.append(p)
        elif isinstance(p, dict):
            # common shapes
            if "text" in p and isinstance(p["text"], str):
                out.append(p["text"])
            elif "content" in p and isinstance(p["content"], str):
                out.append(p["content"])
            elif "content" in p and isinstance(p["content"], list):
                out.append(" ".join(str(x) for x in p["content"]))
            # ignore assets/images
    return " ".join(out)

def extract_message_text(msg):
    if not isinstance(msg, dict): return ""
    content = msg.get("content")
    if isinstance(content, dict):
        return parts_to_text(content.get("parts"))
    if isinstance(content, list):  # sometimes an array of blocks
        pieces = []
        for blk in content:
            if isinstance(blk, dict) and blk.get("type") == "text" and "text" in blk:
                pieces.append(str(blk["text"]))
        return " ".join(pieces)
    if isinstance(content, str):
        return content
    return ""

def parse_conversations_json(p: pathlib.Path, out_name: str):
    try:
        data = json.loads(p.read_text(errors="ignore"))
    except Exception:
        return
    lines = []
    convs = []
    if isinstance(data, dict):
        convs = data.get("conversations") or data.get("items") or []
    if not isinstance(convs, list):
        return

    for c in convs:
        title = c.get("title") or c.get("id") or "conversation"
        lines.append(f"# {title}")
        mapping = c.get("mapping")
        msgs = c.get("messages")

        if isinstance(mapping, dict):
            for node in mapping.values():
                msg = (node or {}).get("message") or {}
                role = (msg.get("author") or {}).get("role") or "user"
                text = extract_message_text(msg)
                if text:
                    lines.append(f"{role}: {text}")

        elif isinstance(msgs, list):
            for m in msgs:
                role = m.get("author","user")
                text = extract_message_text(m)
                if text:
                    lines.append(f"{role}: {text}")

        lines.append("")

    if lines:
        write_txt(out_name, "\n".join(lines))

def parse_chat_html(p: pathlib.Path):
    try:
        soup = BeautifulSoup(p.read_text(errors="ignore"), "html.parser")
    except Exception:
        return
    for tag in soup(["script","style","noscript"]): tag.decompose()
    title = (soup.title.string.strip() if soup.title else p.stem)
    text = f"{title}\n\n{soup.get_text(separator=' ')}"
    write_txt("chat_export_html", text)

def parse_message_feedback(p: pathlib.Path):
    try:
        data = json.loads(p.read_text(errors="ignore"))
    except Exception:
        return
    if not isinstance(data, list): return
    lines = ["# message_feedback"]
    for item in data:
        conv = item.get("conversation_id","")
        msg = item.get("message_id","")
        fb  = item.get("feedback","")
        if fb:
            lines.append(f"conv:{conv} message:{msg} feedback:{fb}")
    write_txt("message_feedback", "\n".join(lines))

# Drive
found = 0
for p in src.rglob("conversations.json"):
    parse_conversations_json(p, "conversations"); found += 1
for p in src.rglob("shared_conversations.json"):
    parse_conversations_json(p, "shared_conversations"); found += 1
for p in src.rglob("chat.html"):
    parse_chat_html(p); found += 1
for p in src.rglob("message_feedback.json"):
    parse_message_feedback(p); found += 1

print(f"Prepared -> {out} (files processed: {found})")
