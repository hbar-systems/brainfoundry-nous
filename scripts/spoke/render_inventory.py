#!/usr/bin/env python3
"""render_inventory.py: turn inventory.sh's TSV into the page the friend sees. Created 2026-11-11 (SPOKE-1).

    python3 render_inventory.py inventory.tsv out.html [--source "label"] [--console URL]

Standard library only. The page holds counts, sizes, kinds, ages and area names; inventory.sh never
sends file names, so there are none to show. One self-contained file: no script from elsewhere.
"""
import html
import json
import sys
from collections import defaultdict

AGES = ["last 30 days", "this year", "1 to 3 years", "older than 3 years"]
FAV = ("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' "
       "height='64' fill='%23000'/%3E%3Ctext x='32' y='46' font-size='44' text-anchor='middle' fill='%23EBEBE6' "
       "font-family='serif'%3E%E2%84%8F%3C/text%3E%3C/svg%3E")


def size(b):
    b = float(b)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if b < 1000 or unit == "TB":
            return f"{b:.0f} {unit}" if unit in ("B", "KB") or b >= 100 else f"{b:.1f} {unit}"
        b /= 1000


def plural(n, one, many):
    return f"{count(n)} {one if int(n) == 1 else many}"


def count(n):
    return f"{int(n):,}".replace(",", " ")


def read(path):
    meta, areas, kinds, ages, bundles, blocked, extra = {}, {}, defaultdict(lambda: [0, 0]), defaultdict(lambda: [0, 0]), defaultdict(lambda: [0, 0]), {}, {}
    for line in open(path, encoding="utf-8", errors="replace"):
        f = line.rstrip("\n").split("\t")
        t = f[0]
        if t == "meta" and len(f) >= 3:
            meta[f[1]] = f[2]
        elif t == "area":
            areas[f[1]] = [int(f[2]), float(f[3])]
        elif t == "kind":
            kinds[f[2]][0] += int(f[3]); kinds[f[2]][1] += float(f[4])
        elif t == "age":
            ages[f[2]][0] += int(f[3]); ages[f[2]][1] += float(f[4])
        elif t == "bundle":
            bundles[f[2]][0] += int(f[3]); bundles[f[2]][1] += float(f[4])
        elif t == "blocked":
            blocked[f[1]] = int(f[2])
        elif t in ("total", "big", "dups"):
            extra[t] = (int(f[1]), float(f[2]))
    return meta, areas, kinds, ages, bundles, blocked, extra


def bars(rows, total, unit="bytes"):
    """rows: [(label, files, bytes)]; one bar per row, length = share of bytes, direct-labelled."""
    top = max([r[2] for r in rows] + [1])
    out = []
    for label, files, b in rows:
        w = 100 * b / top
        share = 100 * b / total if total else 0
        tip = f"{label}: {size(b)}, {count(files)} {'item' if files == 1 else 'items'}, {share:.1f}% of everything counted"
        out.append(
            f'<div class="row" tabindex="0" data-tip="{html.escape(tip)}"><span class="lab">{html.escape(label)}</span>'
            f'<span class="track"><span class="bar" style="width:{max(w, 0.6):.2f}%"></span></span>'
            f'<span class="val">{size(b)}</span><span class="cnt">{count(files)}</span></div>')
    return "\n".join(out)


def main():
    a = sys.argv[1:]
    if len(a) < 2:
        sys.exit(__doc__)
    src, dst = a[0], a[1]
    label = a[a.index("--source") + 1] if "--source" in a else "this computer"
    console = a[a.index("--console") + 1] if "--console" in a else ""
    meta, areas, kinds, ages, bundles, blocked, extra = read(src)
    files, total = extra.get("total", (0, 0))
    dupf, dupb = extra.get("dups", (0, 0))
    bigf, bigb = extra.get("big", (0, 0))
    disk = float(meta.get("disk_kb", 0)) * 1024
    free = float(meta.get("free_kb", 0)) * 1024

    kind_rows = sorted(((k, v[0], v[1]) for k, v in kinds.items()), key=lambda r: -r[2])
    kind_rows += sorted(((k, v[0], v[1]) for k, v in bundles.items()), key=lambda r: -r[2])
    area_rows = sorted(((k, v[0], v[1]) for k, v in areas.items()), key=lambda r: -r[2])
    age_rows = [(g, ages[g][0], ages[g][1]) for g in AGES if g in ages]
    blocked_txt = ", ".join(f"{html.escape(k)} ({count(v)})" for k, v in sorted(blocked.items()))
    facts = [("computer", meta.get("model", "unknown")), ("chip", meta.get("chip", meta.get("arch", ""))),
             ("memory", meta.get("memory", "")), ("system", meta.get("os", "")),
             ("disk", f"{size(disk)}, {size(free)} free" if disk else "")]
    facts_html = "".join(f'<div><span class="mono">{k}</span><span>{html.escape(v)}</span></div>' for k, v in facts if v)
    when = meta.get("finished", meta.get("started", ""))

    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>What is on this computer</title>
<link rel="icon" href="{FAV}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter+Tight:wght@200;300;400&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root{{--ink:#EBEBE6;--dim:rgba(235,235,230,.58);--faint:rgba(235,235,230,.10);--line:rgba(235,235,230,.16)}}
*{{box-sizing:border-box;margin:0;padding:0}}
html,body{{background:#000;color:var(--ink)}}
body{{font:300 17px/1.5 "Inter Tight",system-ui,sans-serif;padding:56px 64px 80px;max-width:1440px;margin:0 auto}}
.mono{{font:500 11px/1.4 "IBM Plex Mono",monospace;letter-spacing:.14em;text-transform:uppercase;color:var(--dim)}}
header{{display:flex;justify-content:space-between;align-items:baseline;gap:24px;border-bottom:1px solid var(--line);padding-bottom:18px;flex-wrap:wrap}}
h1{{font-weight:200;font-size:56px;line-height:1.05;letter-spacing:-.01em;margin:40px 0 14px}}
.lede{{font-size:20px;max-width:60ch}}
.facts{{display:grid;grid-template-columns:repeat(5,1fr);gap:0;margin-top:36px;border-top:1px solid var(--line)}}
.facts div{{padding:14px 16px 16px 0;border-bottom:1px solid var(--line);display:flex;flex-direction:column;gap:6px}}
.facts div+div{{padding-left:16px;border-left:1px solid var(--line)}}
.hero{{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-top:40px}}
.tile{{border:1px solid var(--line);padding:20px 20px 22px}}
.tile .num{{font-weight:200;font-size:44px;line-height:1.1;margin-top:10px}}
.tile p{{font-size:14px;color:var(--dim);margin-top:6px}}
section{{margin-top:56px}}
section>h2{{font-weight:300;font-size:26px;margin:8px 0 18px}}
.row{{display:grid;grid-template-columns:minmax(150px,240px) 1fr 90px 70px;align-items:center;gap:14px;padding:7px 0;border-bottom:1px solid var(--faint);outline:none}}
.row:hover,.row:focus{{background:rgba(235,235,230,.04)}}
.lab{{font-size:15px}}
.track{{height:10px;position:relative}}
.bar{{position:absolute;left:0;top:0;bottom:0;background:var(--ink);border-radius:0 4px 4px 0}}
.val{{font:400 13px "IBM Plex Mono",monospace;text-align:right}}
.cnt{{font:400 12px "IBM Plex Mono",monospace;text-align:right;color:var(--dim)}}
.head{{border-bottom:1px solid var(--line)}}
.head span{{font:500 10px "IBM Plex Mono",monospace;letter-spacing:.14em;text-transform:uppercase;color:var(--dim)}}
.never{{display:grid;grid-template-columns:1fr 1fr;gap:14px}}
.box{{border:1px solid var(--line);padding:20px 22px}}
.box ul{{list-style:none;margin-top:10px}}
.box li{{padding:6px 0;border-bottom:1px solid var(--faint);font-size:15px}}
.ask{{border:1px solid var(--ink);padding:28px 30px;display:flex;justify-content:space-between;align-items:center;gap:28px;flex-wrap:wrap}}
.ask p{{max-width:62ch}}
.btns{{display:flex;gap:10px;flex-wrap:wrap}}
button{{font:500 12px "IBM Plex Mono",monospace;letter-spacing:.12em;text-transform:uppercase;padding:13px 18px;border:1px solid var(--ink);background:#000;color:var(--ink);cursor:pointer;border-radius:0}}
button.yes{{background:var(--ink);color:#000}}
button:focus-visible{{outline:2px solid var(--ink);outline-offset:3px}}
#said{{margin-top:14px;font-size:15px;color:var(--dim);min-height:1.5em}}
#tip{{position:fixed;pointer-events:none;background:#000;border:1px solid var(--ink);padding:8px 10px;font:400 12px "IBM Plex Mono",monospace;max-width:300px;display:none;z-index:9}}
footer{{margin-top:56px;border-top:1px solid var(--line);padding-top:16px}}
@media (max-width:760px){{
 body{{padding:28px 20px 56px}} h1{{font-size:38px;margin-top:28px}} .lede{{font-size:17px}}
 .facts{{grid-template-columns:1fr 1fr}} .facts div,.facts div+div{{padding:12px 10px 12px 0;border-left:0}}
 .hero{{grid-template-columns:1fr 1fr}} .tile .num{{font-size:32px}}
 .row{{grid-template-columns:110px 1fr 66px;gap:10px}} .cnt,.head span:nth-child(4){{display:none}} .lab{{font-size:14px}}
 .never{{grid-template-columns:1fr}}
}}
</style></head><body>
<header><span class="mono">your brain · first look</span><span class="mono">{html.escape(label)} · {html.escape(when)}</span></header>
<h1>What is on this computer</h1>
<p class="lede">Your brain looked at sizes, kinds and dates only. No file name left the computer and nothing was opened, moved or changed.</p>
<div class="facts">{facts_html}</div>

<div class="hero">
 <div class="tile"><span class="mono">counted</span><div class="num">{size(total)}</div><p>{plural(files, "file", "files")} and {plural(sum(v[0] for v in bundles.values()), "library or app", "libraries or apps")}</p></div>
 <div class="tile"><span class="mono">likely copies</span><div class="num">{size(dupb)}</div><p>{plural(dupf, "file has", "files have")} the same name and size as another</p></div>
 <div class="tile"><span class="mono">very large files</span><div class="num">{count(bigf)}</div><p>over 1 GB each, {size(bigb)} together</p></div>
 <div class="tile"><span class="mono">untouched for 3 years</span><div class="num">{size(ages.get("older than 3 years", [0, 0])[1])}</div><p>{plural(ages.get("older than 3 years", [0, 0])[0], "file", "files")}</p></div>
</div>

<section><span class="mono">by kind</span><h2>What it is</h2>
<div class="row head"><span>kind</span><span></span><span style="text-align:right">size</span><span style="text-align:right">items</span></div>
{bars(kind_rows, total)}
</section>

<section><span class="mono">by place</span><h2>Where it is</h2>
<div class="row head"><span>place</span><span></span><span style="text-align:right">size</span><span style="text-align:right">items</span></div>
{bars(area_rows, total)}
</section>

<section><span class="mono">by age</span><h2>When it last changed</h2>
<div class="row head"><span>last changed</span><span></span><span style="text-align:right">size</span><span style="text-align:right">files</span></div>
{bars(age_rows, sum(r[2] for r in age_rows))}
</section>

<section><span class="mono">limits</span><h2>What it did not read</h2>
<div class="never">
 <div class="box"><span class="mono">never read, by design</span><ul>
  <li>Passwords and keychains</li><li>Messages, Mail and other people's conversations</li>
  <li>Browsers: history, cookies, saved logins</li><li>Hidden settings folders and app data (Library)</li>
  <li>Inside the Photos and Music libraries: counted whole, never opened</li></ul></div>
 <div class="box"><span class="mono">macOS said no</span><ul>
  <li>{blocked_txt or "Nothing was refused."}</li>
  <li>{"Full disk access for remote users is off, so these places were not counted. Turning it on in System Settings, Sharing, Remote Login is your choice." if blocked else "Every place it was allowed to look, it could."}</li></ul></div>
</div>
</section>

<section><div class="ask"><p>Next, your brain would propose folders for this, one place at a time, from what you want kept close. It moves nothing until you have read the plan and said yes, and every move can be undone.</p>
<div class="btns"><button class="yes" data-say="Your brain will write a plan for you to read. Nothing moves yet.">Propose a plan</button><button data-say="Your brain stays as it is: it can look, it does not organise.">Not now</button></div></div>
<div id="said" aria-live="polite"></div></section>

<footer><span class="mono">counts and sizes only · read by inventory.sh · {html.escape(meta.get("started", ""))} to {html.escape(meta.get("finished", ""))}{(" · " + html.escape(console)) if console else ""}</span></footer>
<div id="tip" role="tooltip"></div>
<script>
const tip = document.getElementById("tip");
document.querySelectorAll(".row[data-tip]").forEach(r => {{
  const show = e => {{ tip.textContent = r.dataset.tip; tip.style.display = "block";
    const x = (e.clientX || r.getBoundingClientRect().left + 20), y = (e.clientY || r.getBoundingClientRect().top);
    tip.style.left = Math.min(x + 14, innerWidth - 310) + "px"; tip.style.top = (y + 16) + "px"; }};
  r.addEventListener("mousemove", show); r.addEventListener("focus", show);
  r.addEventListener("mouseleave", () => tip.style.display = "none"); r.addEventListener("blur", () => tip.style.display = "none");
}});
document.querySelectorAll("button[data-say]").forEach(b => b.addEventListener("click", () => {{
  document.getElementById("said").textContent = b.dataset.say; }}));
</script>
</body></html>
"""
    open(dst, "w", encoding="utf-8").write(page)
    print(json.dumps({"out": dst, "files": files, "bytes": total}))


if __name__ == "__main__":
    main()
