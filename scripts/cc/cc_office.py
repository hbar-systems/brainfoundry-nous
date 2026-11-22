"""Office files as a page (hbar 2026-11-22: "No preview for this type" on a deck.pptx; most of all for
members who live in Word and PowerPoint). Standard library only: a .pptx, .docx or .xlsx is a zip of
XML, read here into one self-contained HTML page (text, layout, pictures inline), served by the bridge
under a no-script sandbox. Not a faithful renderer (themes, charts, SmartArt, fonts are approximated or
skipped); when a PDF of the same name sits beside the file, the Files pane shows that instead.
"""
from __future__ import annotations

import base64
import html
import posixpath
import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "pr": "http://schemas.openxmlformats.org/package/2006/relationships",
    "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
}
R_ID = "{%s}id" % NS["r"]
R_EMBED = "{%s}embed" % NS["r"]
SUFFIXES = (".pptx", ".docx", ".xlsx")
LEGACY = (".ppt", ".doc", ".xls", ".odt", ".odp", ".ods", ".key", ".pages", ".numbers")
MAX_MEMBER = 60 * 1024 * 1024      # one part of the zip, unpacked
MAX_IMAGES = 80 * 1024 * 1024      # all pictures inlined into one page
MAX_ROWS, MAX_COLS = 2000, 60
IMG_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif",
             ".webp": "image/webp", ".bmp": "image/bmp", ".svg": "image/svg+xml"}
esc = html.escape


class Pkg:
    def __init__(self, path: Path):
        self.z = zipfile.ZipFile(path)
        self.names = set(self.z.namelist())
        self.img_budget = MAX_IMAGES

    def read(self, name: str) -> bytes | None:
        if name not in self.names:
            return None
        if self.z.getinfo(name).file_size > MAX_MEMBER:
            return None
        return self.z.read(name)

    def xml(self, name: str):
        b = self.read(name)
        if b is None:
            return None
        try:
            return ET.fromstring(b)
        except ET.ParseError:
            return None

    def rels(self, part: str) -> dict:
        d, f = posixpath.split(part)
        root = self.xml(posixpath.join(d, "_rels", f + ".rels"))
        out = {}
        if root is None:
            return out
        for r in root.findall("pr:Relationship", NS):
            t = r.get("Target") or ""
            if r.get("TargetMode") == "External":
                out[r.get("Id")] = ("ext", t)
            else:
                out[r.get("Id")] = ("int", posixpath.normpath(posixpath.join(d, t)) if not t.startswith("/") else t.lstrip("/"))
        return out

    def image(self, part: str) -> str | None:
        ext = posixpath.splitext(part)[1].lower()
        mime = IMG_TYPES.get(ext)
        if not mime:
            return None
        b = self.read(part)
        if b is None or len(b) > self.img_budget:
            return None
        self.img_budget -= len(b)
        return f"data:{mime};base64," + base64.b64encode(b).decode()


PAGE_CSS = """
*{box-sizing:border-box}body{margin:0;background:#e9e6e1;color:#222;font:15px/1.45 -apple-system,'Segoe UI',Calibri,Arial,sans-serif}
.bar{position:sticky;top:0;z-index:3;background:#2a2622;color:#efe9df;font:12px ui-monospace,monospace;padding:8px 14px;letter-spacing:.04em}
.bar b{color:#d6b46a;font-weight:600}.wrap{max-width:1100px;margin:0 auto;padding:18px}
.slide{position:relative;width:100%;background:#fff;box-shadow:0 2px 10px rgba(0,0,0,.12);border-radius:4px;overflow:hidden;container-type:inline-size;margin:0 0 6px}
.slide .sh{position:absolute;overflow:hidden}.slide .sh p{margin:0}.slide img{position:absolute;object-fit:contain}
.num{font:11px ui-monospace,monospace;color:#7a7268;margin:0 0 4px}.notes{font-size:13px;color:#4b443d;background:#f6f3ee;border-left:3px solid #c9a55c;padding:6px 10px;margin:0 0 22px;white-space:pre-wrap}
.doc{background:#fff;max-width:820px;margin:0 auto;padding:56px 64px;box-shadow:0 2px 10px rgba(0,0,0,.12);border-radius:4px}
.doc h1,.doc h2,.doc h3{line-height:1.25;margin:1em 0 .35em}.doc p{margin:0 0 .6em}.doc img{max-width:100%}
table{border-collapse:collapse;margin:.4em 0 1em;background:#fff}td,th{border:1px solid #d5cfc6;padding:3px 7px;vertical-align:top;font-size:13px}
th{background:#f1ece4;font-weight:600;color:#5a5249}.sheet{overflow:auto;max-height:80vh;margin-bottom:20px}.miss{color:#9a8f82;font-style:italic}
h2.sn{font:600 13px ui-monospace,monospace;letter-spacing:.08em;text-transform:uppercase;color:#6a6258;margin:18px 0 6px}
"""


def page(title: str, kind: str, body: str, note: str = "") -> bytes:
    bar = f'<div class="bar"><b>{esc(kind)}</b> &middot; {esc(title)}{(" &middot; " + esc(note)) if note else ""} &middot; preview, not the original layout in every detail</div>'
    return (f'<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{esc(title)}</title><style>{PAGE_CSS}</style></head><body>{bar}<div class="wrap">{body}</div></body></html>').encode()


# ---------- PowerPoint ----------

def _xfrm(el):
    x = el.find(".//a:xfrm", NS) if el is not None else None
    if x is None:
        return None
    off, ext = x.find("a:off", NS), x.find("a:ext", NS)
    if off is None or ext is None:
        return None
    return [int(off.get("x", 0)), int(off.get("y", 0)), int(ext.get("cx", 0)), int(ext.get("cy", 0))]


def _ph_key(sp):
    ph = sp.find("./*/p:nvPr/p:ph", NS)
    if ph is None:
        return None
    return (ph.get("type") or "body", ph.get("idx"))


def _ph_table(root):
    """placeholder (type, idx) -> (xfrm, default size in 1/100 pt) for a layout or master"""
    out = {}
    if root is None:
        return out
    for sp in root.iter("{%s}sp" % NS["p"]):
        k = _ph_key(sp)
        if k:
            out[k] = _xfrm(sp.find("p:spPr", NS))
    return out


def _find_ph(tables, key):
    typ, idx = key
    for t in tables:
        for (ty, ix), xf in t.items():
            if xf and ((idx is not None and ix == idx) or (ty == typ)):
                return xf
        for (ty, ix), xf in t.items():   # a title is a title whatever its kind of title
            if xf and typ in ("title", "ctrTitle") and ty in ("title", "ctrTitle"):
                return xf
    return None


def _color(el):
    c = el.find("a:solidFill/a:srgbClr", NS) if el is not None else None
    return "#" + c.get("val") if c is not None and re.fullmatch(r"[0-9A-Fa-f]{6}", c.get("val") or "") else None


def _runs_a(p, base_sz, cx_pt):
    out = []
    for r in p:
        tag = r.tag.split("}")[1]
        if tag == "br":
            out.append("<br>")
            continue
        if tag not in ("r", "fld"):
            continue
        t = r.find("a:t", NS)
        if t is None or not t.text:
            continue
        rp = r.find("a:rPr", NS)
        st = []
        sz = int(rp.get("sz")) if rp is not None and (rp.get("sz") or "").isdigit() else None
        if sz:
            st.append(f"font-size:{sz / 100 / cx_pt * 100:.3f}cqw")
        if rp is not None and rp.get("b") == "1":
            st.append("font-weight:700")
        if rp is not None and rp.get("i") == "1":
            st.append("font-style:italic")
        if rp is not None and rp.get("u") not in (None, "none"):
            st.append("text-decoration:underline")
        col = _color(rp)
        if col:
            st.append(f"color:{col}")
        out.append(f'<span style="{";".join(st)}">{esc(t.text)}</span>' if st else esc(t.text))
    return "".join(out)


def _txbody(tb, base_sz, cx_pt, bullets):
    paras = []
    for p in tb.findall("a:p", NS):
        ppr = p.find("a:pPr", NS)
        lvl = int(ppr.get("lvl", 0)) if ppr is not None and (ppr.get("lvl") or "0").isdigit() else 0
        algn = {"ctr": "center", "r": "right", "just": "justify"}.get(ppr.get("algn") if ppr is not None else "", "left")
        inner = _runs_a(p, base_sz, cx_pt)
        if not inner:
            paras.append("<p>&nbsp;</p>")
            continue
        no_bul = ppr is not None and ppr.find("a:buNone", NS) is not None
        has_bul = ppr is not None and (ppr.find("a:buChar", NS) is not None or ppr.find("a:buAutoNum", NS) is not None)
        bul = "&bull;&nbsp;" if (has_bul or (bullets and not no_bul)) else ""
        paras.append(f'<p style="text-align:{algn};padding-left:{lvl * 1.6 + (1.1 if bul else 0):.1f}em;text-indent:{-1.1 if bul else 0}em">{bul}{inner}</p>')
    return "".join(paras)


def _table_a(tbl):
    rows = []
    for tr in tbl.findall("a:tr", NS):
        cells = []
        for tc in tr.findall("a:tc", NS):
            txt = "<br>".join(esc("".join(t.text or "" for t in p.iter("{%s}t" % NS["a"]))) for p in tc.iter("{%s}p" % NS["a"]))
            cells.append(f"<td>{txt}</td>")
        rows.append("<tr>" + "".join(cells) + "</tr>")
    return '<table style="width:100%;height:100%;font-size:1.3cqw">' + "".join(rows) + "</table>"


def _pos(xf, cx, cy):
    x, y, w, h = xf
    return f"left:{x / cx * 100:.3f}%;top:{y / cy * 100:.3f}%;width:{w / cx * 100:.3f}%;height:{h / cy * 100:.3f}%"


def pptx_html(path: Path) -> bytes:
    k = Pkg(path)
    pres = k.xml("ppt/presentation.xml")
    if pres is None:
        return page(path.name, "PowerPoint", '<p class="miss">This file does not open as a PowerPoint deck.</p>')
    sz = pres.find("p:sldSz", NS)
    cx, cy = (int(sz.get("cx")), int(sz.get("cy"))) if sz is not None else (12192000, 6858000)
    cx_pt = cx / 12700
    prels = k.rels("ppt/presentation.xml")
    order = [prels.get(s.get(R_ID), ("", ""))[1] for s in pres.findall("p:sldIdLst/p:sldId", NS)]
    out = []
    for n, part in enumerate([o for o in order if o], 1):
        root = k.xml(part)
        if root is None:
            continue
        rels = k.rels(part)
        layout = next((t for kind, t in rels.values() if kind == "int" and "slideLayout" in t), None)
        tables = []
        if layout:
            tables.append(_ph_table(k.xml(layout)))
            master = next((t for kind, t in k.rels(layout).values() if kind == "int" and "slideMaster" in t), None)
            if master:
                tables.append(_ph_table(k.xml(master)))
        bg = _color(root.find(".//p:bg/p:bgPr", NS))
        shapes = []

        def walk(tree, gx=None):
            for el in tree:
                tag = el.tag.split("}")[1]
                xf = _xfrm(el.find("p:spPr", NS)) if tag in ("sp", "cxnSp") else _xfrm(el.find("p:xfrm", NS)) if tag == "graphicFrame" else _xfrm(el.find("p:spPr", NS)) if tag == "pic" else None
                if tag == "grpSp":
                    g = el.find("p:grpSpPr/a:xfrm", NS)
                    m = None
                    if g is not None and g.find("a:chOff", NS) is not None:
                        o, e, co, ce = g.find("a:off", NS), g.find("a:ext", NS), g.find("a:chOff", NS), g.find("a:chExt", NS)
                        m = (int(o.get("x")), int(o.get("y")), int(e.get("cx")) / max(1, int(ce.get("cx"))), int(e.get("cy")) / max(1, int(ce.get("cy"))), int(co.get("x")), int(co.get("y")))
                    walk(el, m or gx)
                    continue
                key = _ph_key(el) if tag == "sp" else None
                if xf is None and key:
                    xf = _find_ph(tables, key)
                if xf is None:
                    continue
                if gx:
                    ox, oy, sx, sy, cox, coy = gx
                    xf = [ox + (xf[0] - cox) * sx, oy + (xf[1] - coy) * sy, xf[2] * sx, xf[3] * sy]
                pos = _pos(xf, cx, cy)
                if tag == "pic":
                    b = el.find(".//a:blip", NS)
                    tgt = rels.get(b.get(R_EMBED)) if b is not None else None
                    src = k.image(tgt[1]) if tgt and tgt[0] == "int" else None
                    shapes.append(f'<img alt="" src="{src}" style="{pos}">' if src else f'<div class="sh miss" style="{pos};border:1px dashed #ccc;display:grid;place-items:center;font-size:1.2cqw">picture</div>')
                elif tag == "graphicFrame":
                    tbl = el.find(".//a:tbl", NS)
                    shapes.append(f'<div class="sh" style="{pos}">{_table_a(tbl)}</div>' if tbl is not None else f'<div class="sh miss" style="{pos};border:1px dashed #ccc;display:grid;place-items:center;font-size:1.2cqw">chart or diagram</div>')
                elif tag == "sp":
                    fill = _color(el.find("p:spPr", NS))
                    tb = el.find("p:txBody", NS)
                    title = bool(key and key[0] in ("title", "ctrTitle"))
                    base = 3600 if title else 1800
                    body = _txbody(tb, base, cx_pt, bullets=bool(key and key[0] in ("body", "obj") and key[1] is not None)) if tb is not None else ""
                    anchor = tb.find("a:bodyPr", NS).get("anchor") if tb is not None and tb.find("a:bodyPr", NS) is not None else None
                    jc = {"ctr": "center", "b": "flex-end"}.get(anchor or ("ctr" if title else "t"), "flex-start")
                    style = f"{pos};font-size:{base / 100 / cx_pt * 100:.3f}cqw;display:flex;flex-direction:column;justify-content:{jc};padding:0.4cqw 0.7cqw" + (";font-weight:600" if title else "") + (f";background:{fill}" if fill else "")
                    if body or fill:
                        shapes.append(f'<div class="sh" style="{style}">{body}</div>')

        tree = root.find("p:cSld/p:spTree", NS)
        if tree is not None:
            walk(tree)
        notes = ""
        np_ = next((t for kind, t in rels.values() if kind == "int" and "notesSlide" in t), None)
        if np_:
            nr = k.xml(np_)
            if nr is not None:
                txt = []
                for sp in nr.iter("{%s}sp" % NS["p"]):
                    kk = _ph_key(sp)
                    if kk and kk[0] == "body":
                        txt += ["".join(t.text or "" for t in p.iter("{%s}t" % NS["a"])) for p in sp.iter("{%s}p" % NS["a"])]
                t = "\n".join(txt).strip()
                if t:
                    notes = f'<div class="notes">{esc(t)}</div>'
        out.append(f'<p class="num">slide {n}</p><div class="slide" style="aspect-ratio:{cx}/{cy}{";background:" + bg if bg else ""}">{"".join(shapes)}</div>{notes or "<div style=height:18px></div>"}')
    return page(path.name, "PowerPoint", "".join(out) or '<p class="miss">No slides in this deck.</p>', f"{len(out)} slides")


# ---------- Word ----------

def _runs_w(p, rels, k):
    out = []
    for r in p.iter():
        tag = r.tag.split("}")[1]
        if tag == "r" and r.tag.startswith("{%s}" % NS["w"]):
            rp = r.find("w:rPr", NS)
            parts = []
            for c in r:
                ct = c.tag.split("}")[1]
                if ct == "t":
                    parts.append(esc(c.text or ""))
                elif ct == "tab":
                    parts.append("&emsp;")
                elif ct in ("br", "cr"):
                    parts.append("<br>")
                elif ct == "drawing":
                    b = c.find(".//a:blip", NS)
                    tgt = rels.get(b.get(R_EMBED)) if b is not None else None
                    src = k.image(tgt[1]) if tgt and tgt[0] == "int" else None
                    parts.append(f'<img alt="" src="{src}">' if src else '<span class="miss">[picture]</span>')
            s = "".join(parts)
            if not s:
                continue
            if rp is not None:
                if rp.find("w:b", NS) is not None and rp.find("w:b", NS).get("{%s}val" % NS["w"]) not in ("0", "false"):
                    s = f"<b>{s}</b>"
                if rp.find("w:i", NS) is not None and rp.find("w:i", NS).get("{%s}val" % NS["w"]) not in ("0", "false"):
                    s = f"<i>{s}</i>"
                u = rp.find("w:u", NS)
                if u is not None and u.get("{%s}val" % NS["w"]) not in ("none", None):
                    s = f"<u>{s}</u>"
                hl = rp.find("w:highlight", NS)
                if hl is not None:
                    s = f'<mark>{s}</mark>'
            out.append(s)
    return "".join(out)


def _para_w(p, rels, k):
    ppr = p.find("w:pPr", NS)
    style = ""
    if ppr is not None and ppr.find("w:pStyle", NS) is not None:
        style = (ppr.find("w:pStyle", NS).get("{%s}val" % NS["w"]) or "").lower()
    inner = _runs_w(p, rels, k)
    m = re.match(r"(?:heading|berschrift|заголовок)\s*([1-6])", style)
    if style in ("title", "titel"):
        return f"<h1>{inner}</h1>" if inner else ""
    if m:
        lv = min(3, int(m.group(1)) + (0 if int(m.group(1)) > 1 else 0))
        return f"<h{lv}>{inner}</h{lv}>" if inner else ""
    num = ppr is not None and ppr.find("w:numPr", NS) is not None
    ilvl = 0
    if num:
        il = ppr.find("w:numPr/w:ilvl", NS)
        ilvl = int(il.get("{%s}val" % NS["w"]) or 0) if il is not None else 0
    jc = ppr.find("w:jc", NS).get("{%s}val" % NS["w"]) if ppr is not None and ppr.find("w:jc", NS) is not None else ""
    align = {"center": "center", "right": "right", "both": "justify", "end": "right"}.get(jc, "")
    st = (f"text-align:{align};" if align else "") + (f"padding-left:{1.4 + ilvl * 1.4}em;text-indent:-1em;" if num else "")
    return f'<p style="{st}">{"&bull;&ensp;" if num else ""}{inner or "&nbsp;"}</p>'


def _body_w(el, rels, k):
    out = []
    for c in el:
        tag = c.tag.split("}")[1]
        if tag == "p":
            out.append(_para_w(c, rels, k))
        elif tag == "tbl":
            rows = []
            for tr in c.findall("w:tr", NS):
                rows.append("<tr>" + "".join(f"<td>{_body_w(tc, rels, k)}</td>" for tc in tr.findall("w:tc", NS)) + "</tr>")
            out.append("<table>" + "".join(rows) + "</table>")
        elif tag == "sdt":
            sc = c.find("w:sdtContent", NS)
            if sc is not None:
                out.append(_body_w(sc, rels, k))
    return "".join(out)


def docx_html(path: Path) -> bytes:
    k = Pkg(path)
    root = k.xml("word/document.xml")
    if root is None:
        return page(path.name, "Word", '<p class="miss">This file does not open as a Word document.</p>')
    body = root.find("w:body", NS)
    html_ = _body_w(body, k.rels("word/document.xml"), k) if body is not None else ""
    return page(path.name, "Word", f'<div class="doc">{html_}</div>')


# ---------- Excel ----------

def _col(ref):
    m = re.match(r"([A-Z]+)(\d+)", ref or "")
    if not m:
        return None, None
    n = 0
    for ch in m.group(1):
        n = n * 26 + ord(ch) - 64
    return n - 1, int(m.group(2)) - 1


def _letters(i):
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def xlsx_html(path: Path) -> bytes:
    k = Pkg(path)
    wb = k.xml("xl/workbook.xml")
    if wb is None:
        return page(path.name, "Excel", '<p class="miss">This file does not open as an Excel workbook.</p>')
    shared = []
    ss = k.xml("xl/sharedStrings.xml")
    if ss is not None:
        for si in ss.findall("s:si", NS):
            shared.append("".join(t.text or "" for t in si.iter("{%s}t" % NS["s"])))
    rels = k.rels("xl/workbook.xml")
    out = []
    for sh in wb.findall("s:sheets/s:sheet", NS):
        tgt = rels.get(sh.get(R_ID))
        root = k.xml(tgt[1]) if tgt else None
        if root is None:
            continue
        grid, maxc, cut = {}, 0, False
        for row in root.iter("{%s}row" % NS["s"]):
            for c in row.findall("s:c", NS):
                ci, ri = _col(c.get("r"))
                if ci is None:
                    continue
                if ri >= MAX_ROWS or ci >= MAX_COLS:
                    cut = True
                    continue
                t, v = c.get("t"), c.find("s:v", NS)
                if t == "s" and v is not None and (v.text or "").isdigit():
                    val = shared[int(v.text)] if int(v.text) < len(shared) else ""
                elif t == "inlineStr":
                    val = "".join(x.text or "" for x in c.iter("{%s}t" % NS["s"]))
                elif t == "b" and v is not None:
                    val = "TRUE" if v.text == "1" else "FALSE"
                else:
                    val = v.text if v is not None and v.text is not None else ""
                    if re.fullmatch(r"-?\d+\.\d{6,}(E-?\d+)?", val):
                        try:
                            val = f"{float(val):.6g}"
                        except ValueError:
                            pass
                if val != "":
                    grid[(ri, ci)] = val
                    maxc = max(maxc, ci)
        maxr = max((r for r, _ in grid), default=-1)
        head = "<tr><th></th>" + "".join(f"<th>{_letters(i)}</th>" for i in range(maxc + 1)) + "</tr>"
        rows = "".join("<tr><th>%d</th>%s</tr>" % (r + 1, "".join(f"<td>{esc(grid.get((r, c), ''))}</td>" for c in range(maxc + 1))) for r in range(maxr + 1))
        note = f'<p class="miss">Showing the first {MAX_ROWS} rows and {MAX_COLS} columns.</p>' if cut else ""
        out.append(f'<h2 class="sn">{esc(sh.get("name") or "sheet")}</h2>{note}<div class="sheet"><table>{head}{rows}</table></div>' if grid else f'<h2 class="sn">{esc(sh.get("name") or "sheet")}</h2><p class="miss">empty</p>')
    return page(path.name, "Excel", "".join(out) or '<p class="miss">No sheets.</p>', f"{len(out)} sheets")


def to_html(path: Path) -> bytes:
    s = path.suffix.lower()
    try:
        if s == ".pptx":
            return pptx_html(path)
        if s == ".docx":
            return docx_html(path)
        if s == ".xlsx":
            return xlsx_html(path)
    except (zipfile.BadZipFile, KeyError, ValueError, OSError) as e:
        return page(path.name, "Office", f'<p class="miss">This file could not be read ({esc(type(e).__name__)}). Download it to open it.</p>')
    return page(path.name, "Office", '<p class="miss">This is an older or non-Microsoft format the preview does not read yet. Download it, or open it and save it as .docx, .pptx or .xlsx.</p>')


def sibling_pdf(path: Path) -> Path | None:
    c = path.with_suffix(".pdf")
    try:
        return c if c.is_file() else None
    except OSError:
        return None
