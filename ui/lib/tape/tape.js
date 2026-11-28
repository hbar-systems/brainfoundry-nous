// The memo tape on the console (TAPE-2, 2026-11-14). Lifted from the tape page a watcher's repo served as a
// raw file (memos/index.html, TALK-1 5f9b0e6), which the console stopped running on its own origin on
// 2026-11-13 (desk pages are sandboxed). Here it is the console's own code: it reads and writes only the tape
// folder through /cc/tape (scripts/cc/cc_tape.py) and records through the console's /cc/upload.
// mountTape(root, opts) draws it into root and returns a function that takes it down again.
//   opts: {dir, vocab, signer, world, demo, expose}  (from GET /cc/tape, plus the page's ?demo=1)
/* eslint-disable no-empty, no-unused-vars */
export const TAPE_CSS = ".tp{--font-body:\"Crimson Pro\",Georgia,serif;--act:var(--accent);--file:#8a8075;--archive:#6b8cce;--delete:#c87878;--merge:#8d7bb5;--ok:#88a868;--ink:color-mix(in oklab,var(--text) 86%,transparent);position:relative;isolation:isolate;min-height:calc(100vh - var(--nav-h, 52px))}\n.tp,.tp *{box-sizing:border-box}\n.tp{background:var(--bg);color:var(--text);font-family:var(--font-body);font-size:17px;line-height:1.5;-webkit-font-smoothing:antialiased;overflow-x:hidden}\n.tp::before{content:\"\";position:fixed;inset:0;pointer-events:none;z-index:0;\n  background:radial-gradient(1200px 600px at 20% -10%,color-mix(in oklab,var(--accent) 9%,transparent),transparent 60%),\n             radial-gradient(900px 500px at 110% 110%,color-mix(in oklab,var(--accent) 6%,transparent),transparent 60%)}\n.tp::after{content:\"\";position:fixed;inset:-50%;pointer-events:none;z-index:0;opacity:.035;mix-blend-mode:overlay;\n  background-image:url(\"data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='160' height='160'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='.9' numOctaves='2' stitchTiles='stitch'/></filter><rect width='100%' height='100%' filter='url(%23n)'/></svg>\")}\n.tp a{color:var(--accent)}\n.tp button{font:inherit;color:inherit;background:none;border:0;padding:0;cursor:pointer}\n.tp input,.tp textarea{font:inherit;color:var(--text);background:transparent;border:0;outline:0}\n.tp ::selection{background:color-mix(in oklab,var(--accent) 35%,transparent)}\n.tp .mono{font-family:var(--font-mono);font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--muted)}\n.tp #app{position:relative;z-index:1;display:grid;grid-template-columns:272px minmax(0,1fr);min-height:calc(100vh - var(--nav-h, 52px))}\n.tp #shelf{border-right:1px solid var(--border);padding:28px 0 40px;background:color-mix(in oklab,var(--surface) 55%,transparent);backdrop-filter:blur(6px)}\n.tp #main{min-width:0;padding:0 48px 120px}\n@media (max-width:900px){.tp #app{grid-template-columns:minmax(0,1fr)}\n.tp #shelf{min-width:0}\n.tp #shelf{border-right:0;border-bottom:1px solid var(--border);padding:16px 0}\n.tp #main{padding:0 20px 100px}\n.tp #list{display:flex;overflow-x:auto;gap:8px;padding:0 16px}\n.tp #list .mi{min-width:220px}}\n.tp #status{position:sticky;top:var(--nav-h, 52px);z-index:30;font-family:var(--font-mono);font-size:12px;letter-spacing:.04em;padding:0 48px;height:0;overflow:visible;pointer-events:none}\n.tp #status span{display:inline-block;transform:translateY(10px);padding:6px 12px;border-radius:999px;background:var(--surface2);border:1px solid var(--border);color:var(--text);opacity:0;transition:opacity .3s}\n.tp #status.show span{opacity:1;pointer-events:auto}\n.tp #status.err span{border-color:color-mix(in oklab,var(--delete) 60%,transparent);color:var(--delete)}\n.tp #status.ok span{border-color:color-mix(in oklab,var(--ok) 60%,transparent)}\n.tp #shelf h1{margin:0 24px 18px;font-family:var(--font-display);font-weight:400;font-size:15px;letter-spacing:.32em;text-transform:uppercase;color:var(--muted)}\n.tp #shelf h1 b{color:var(--accent);font-weight:400}\n.tp #shelf h1 .views{display:inline-flex;gap:14px;margin-left:14px;vertical-align:1px}\n.tp #shelf h1 .views button{font-family:var(--font-mono);font-size:10px;letter-spacing:.14em;text-transform:uppercase;color:var(--muted);border-bottom:1px solid transparent;padding-bottom:2px;transition:color .2s,border-color .2s}\n.tp #shelf h1 .views button:hover{color:var(--accent)}\n.tp #shelf h1 .views button.on{color:var(--accent);border-bottom-color:color-mix(in oklab,var(--accent) 40%,transparent)}\n.tp .mi{display:block;width:100%;text-align:left;padding:12px 24px 12px 21px;border-left:3px solid transparent;transition:background .25s,border-color .25s;position:relative}\n.tp .mi:hover{background:color-mix(in oklab,var(--surface2) 70%,transparent)}\n.tp .mi.sel{border-left-color:var(--accent);background:color-mix(in oklab,var(--surface2) 90%,transparent)}\n.tp .mi .t{display:block;font-family:var(--font-display);font-size:14.5px;line-height:1.3;color:var(--text);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}\n.tp .mi .m{display:flex;gap:10px;align-items:center;margin-top:6px}\n.tp .mi .m span{font-family:var(--font-mono);font-size:10.5px;letter-spacing:.1em;text-transform:uppercase;color:var(--muted)}\n.tp .mi canvas{display:block;width:100%;height:22px;margin-top:8px;opacity:.75;cursor:pointer}\n.tp .mi canvas:hover{opacity:1}\n.tp .mi.sel canvas{opacity:1}\n.tp .pip{display:inline-block;width:6px;height:6px;border-radius:50%;background:var(--muted);vertical-align:middle;margin-right:6px}\n.tp .pip.decided{background:var(--accent)}\n.tp .pip.filed{background:var(--ok)}\n.tp .pip.error{background:var(--delete)}\n.tp .pip.working{background:var(--accent);animation:tp-breathe 1.6s ease-in-out infinite}\n@keyframes tp-breathe{0%,100%{opacity:.25;transform:scale(.8)}50%{opacity:1;transform:scale(1.15)}}\n.tp .empty{color:var(--muted);font-style:italic;padding:12px 24px}\n.tp #plate{margin:40px 0 8px;padding:34px 36px 30px;border:1px solid var(--border);border-radius:18px;position:relative;overflow:hidden;\n  background:linear-gradient(160deg,color-mix(in oklab,var(--surface2) 90%,transparent),color-mix(in oklab,var(--surface) 70%,transparent));\n  transition:border-color .3s,box-shadow .3s}\n.tp #plate.over{border-color:var(--accent);box-shadow:0 0 0 1px var(--accent) inset,0 24px 80px -40px color-mix(in oklab,var(--accent) 60%,transparent)}\n.tp #plate .ring{position:absolute;right:34px;top:50%;width:84px;height:84px;margin-top:-42px;border-radius:50%;border:1px solid color-mix(in oklab,var(--accent) 60%,transparent);opacity:.9}\n.tp #plate .ring::before,.tp #plate .ring::after{content:\"\";position:absolute;inset:-1px;border-radius:50%;border:1px solid color-mix(in oklab,var(--accent) 45%,transparent);animation:tp-ring 3.6s ease-out infinite}\n.tp #plate .ring::after{animation-delay:1.8s}\n@keyframes tp-ring{0%{transform:scale(.6);opacity:.9}100%{transform:scale(1.9);opacity:0}}\n.tp #plate .ring i{position:absolute;left:50%;top:50%;width:10px;height:10px;margin:-5px;border-radius:50%;background:var(--accent);box-shadow:0 0 18px var(--accent)}\n.tp #plate h2{margin:0;font-family:var(--font-display);font-weight:400;font-size:34px;line-height:1.1;letter-spacing:-.01em}\n.tp #plate h2 em{font-style:italic;color:var(--accent)}\n.tp #plate p{margin:10px 0 0;max-width:620px;color:color-mix(in oklab,var(--text) 70%,var(--muted));font-size:16.5px}\n.tp #plate .ways{display:flex;flex-wrap:wrap;gap:10px 22px;margin-top:18px;align-items:center}\n.tp .lnk{font-family:var(--font-mono);font-size:11.5px;letter-spacing:.12em;text-transform:uppercase;color:var(--accent);border-bottom:1px solid color-mix(in oklab,var(--accent) 40%,transparent);padding-bottom:2px;transition:border-color .2s}\n.tp .lnk:hover{border-bottom-color:var(--accent)}\n.tp #plate .words{display:none;margin-top:18px;border-top:1px solid var(--border);padding-top:14px}\n.tp #plate.words-open .words{display:block}\n.tp #txt{width:100%;min-height:76px;resize:vertical;font-size:17px;line-height:1.5;color:var(--text)}\n.tp #txt::placeholder{color:var(--muted);font-style:italic}\n.tp #progs{margin-top:10px}\n.tp .prog{font-family:var(--font-mono);font-size:11.5px;letter-spacing:.06em;color:var(--muted);margin-top:8px}\n.tp .prog .bar{height:1px;background:var(--border);margin-top:6px;overflow:hidden}\n.tp .prog .bar i{display:block;height:100%;width:0;background:var(--accent);transition:width .3s}\n.tp #talk{display:flex;align-items:center;gap:20px;margin-top:22px;padding:20px 0 4px;border-top:1px solid var(--border)}\n.tp #plate .ring{display:none}\n.tp #recBtn{flex:none;position:relative;width:76px;height:76px;border-radius:50%;border:1px solid color-mix(in oklab,var(--accent) 60%,transparent);\n  background:radial-gradient(circle at 50% 40%,color-mix(in oklab,var(--accent) 18%,var(--surface2)),var(--surface2));transition:transform .15s,border-color .3s,box-shadow .3s;touch-action:manipulation;-webkit-tap-highlight-color:transparent}\n.tp #recBtn:active{transform:scale(.96)}\n.tp #recBtn::before{content:\"\";position:absolute;left:50%;top:50%;width:26px;height:26px;margin:-13px;border-radius:50%;background:var(--accent);box-shadow:0 0 20px color-mix(in oklab,var(--accent) 70%,transparent);transition:border-radius .25s,width .25s,height .25s,margin .25s,background .25s}\n.tp #talk.on #recBtn{border-color:var(--delete);box-shadow:0 0 0 calc(var(--lvl,0)*14px) color-mix(in oklab,var(--delete) 22%,transparent)}\n.tp #talk.on #recBtn::before{width:22px;height:22px;margin:-11px;border-radius:5px;background:var(--delete);box-shadow:0 0 18px color-mix(in oklab,var(--delete) 60%,transparent)}\n.tp #talk.busy #recBtn{opacity:.5;pointer-events:none}\n.tp #talk .tk{flex:1;min-width:0}\n.tp #talk .tk b{display:block;font-family:var(--font-display);font-weight:400;font-size:19px;line-height:1.2}\n.tp #talk .tk b em{font-style:italic;color:var(--accent)}\n.tp #recClock{font-family:var(--font-mono);font-size:26px;letter-spacing:.06em;color:var(--text);font-variant-numeric:tabular-nums;display:none}\n.tp #talk.on #recClock,.tp #talk.busy #recClock{display:block}\n.tp #talk.on .tk b,.tp #talk.busy .tk b{display:none}\n.tp #recLvl{display:block;width:100%;height:28px;margin-top:6px}\n.tp #talk:not(.on) #recLvl{display:none}\n.tp #recNote{display:block;margin-top:4px;text-transform:none;letter-spacing:.06em}\n@media (max-width:900px){.tp #talk{gap:16px}\n.tp #recBtn{width:84px;height:84px}}\n.tp #memo{margin-top:56px}\n.tp .hdr{display:flex;align-items:flex-end;gap:24px;flex-wrap:wrap}\n.tp .hdr .kicker{width:100%}\n.tp .hdr h2{margin:6px 0 0;font-family:var(--font-display);font-weight:400;font-size:clamp(30px,4vw,46px);line-height:1.08;letter-spacing:-.015em;max-width:900px;cursor:text}\n.tp .hdr h2:hover{text-decoration:underline;text-decoration-color:color-mix(in oklab,var(--accent) 50%,transparent);text-underline-offset:8px;text-decoration-thickness:1px}\n.tp .hdr input{font-family:var(--font-display);font-size:clamp(30px,4vw,46px);line-height:1.08;width:100%;border-bottom:1px solid var(--accent)}\n.tp .meta{display:flex;flex-wrap:wrap;gap:6px 22px;margin-top:14px}\n.tp .meta span{font-family:var(--font-mono);font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--muted)}\n.tp .meta span.stage{color:var(--accent)}\n.tp .summary{margin:26px 0 0;max-width:760px;font-size:19.5px;line-height:1.55;font-weight:300;color:color-mix(in oklab,var(--text) 92%,transparent)}\n.tp .themes{display:flex;flex-wrap:wrap;gap:8px;margin-top:16px}\n.tp .themes span{font-family:var(--font-mono);font-size:10.5px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted);border:1px solid var(--border);border-radius:999px;padding:4px 10px}\n.tp .errbox{margin-top:20px;padding:12px 16px;border-left:2px solid var(--delete);color:var(--delete);font-family:var(--font-mono);font-size:12.5px}\n.tp .working{margin-top:20px;font-family:var(--font-mono);font-size:12px;letter-spacing:.08em;color:var(--accent)}\n.tp .next{margin-top:12px;padding:10px 14px;border-left:2px solid var(--accent);font-family:var(--font-mono);font-size:12px;line-height:1.5;letter-spacing:.04em;color:var(--text)}\n.tp .next b{font-weight:400;color:var(--accent)}\n.tp .working i{display:inline-block;width:7px;height:7px;border-radius:50%;background:var(--accent);margin-right:10px;animation:tp-breathe 1.6s ease-in-out infinite;vertical-align:middle}\n.tp #tape{position:relative;margin-top:36px;height:150px;user-select:none;cursor:pointer}\n.tp #tape canvas{position:absolute;inset:0;width:100%;height:100%;display:block}\n.tp #tape .lab{position:absolute;top:0;font-family:var(--font-mono);font-size:10.5px;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);white-space:nowrap;pointer-events:none;transform:translateY(-2px);opacity:0;transition:opacity .25s}\n.tp #tape:hover .lab,.tp #tape .lab.on{opacity:1}\n.tp #tape .lab.on{color:var(--accent)}\n.tp #tape .time{position:absolute;bottom:-18px;font-family:var(--font-mono);font-size:10px;letter-spacing:.12em;color:var(--muted)}\n.tp #tape .head{position:absolute;top:0;bottom:0;width:1px;background:var(--accent);box-shadow:0 0 12px var(--accent);display:none;pointer-events:none}\n.tp #tape .head::after{content:\"\";position:absolute;left:-4px;top:-4px;width:9px;height:9px;border-radius:50%;background:var(--accent)}\n.tp .tape-note{margin-top:28px;font-family:var(--font-mono);font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted);display:flex;gap:26px;flex-wrap:wrap}\n.tp .tape-note b{font-weight:400;color:var(--text)}\n.tp .tape-note .sw{display:inline-block;width:10px;height:10px;border-radius:2px;vertical-align:-1px;margin-right:8px}\n.tp .bar{position:sticky;top:0;z-index:20;margin:40px -48px 0;padding:14px 48px;display:flex;align-items:center;gap:22px;flex-wrap:wrap;\n  background:color-mix(in oklab,var(--bg) 82%,transparent);backdrop-filter:blur(10px);border-bottom:1px solid var(--border)}\n@media (max-width:900px){.tp .bar{margin:40px -20px 0;padding:12px 20px}}\n.tp .bar .info{font-family:var(--font-mono);font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted);margin-left:auto}\n.tp .bar .info b{font-weight:400;color:var(--text)}\n.tp .bar .filed{color:var(--ok)}\n.tp .act{font-family:var(--font-mono);font-size:11.5px;letter-spacing:.14em;text-transform:uppercase;padding:9px 16px;border:1px solid var(--border);border-radius:999px;color:var(--text);transition:all .2s;background:transparent}\n.tp .act:hover:not(:disabled){border-color:var(--accent);color:var(--accent)}\n.tp .act:disabled{opacity:.35;cursor:default}\n.tp .act.gold{background:var(--accent);color:var(--bg);border-color:var(--accent)}\n.tp .act.gold:hover{filter:brightness(1.08);color:var(--bg)}\n.tp .barnote{margin:12px 0 0;letter-spacing:.1em}\n.tp #bits{margin-top:14px}\n.tp .bit{position:relative;display:grid;grid-template-columns:64px minmax(0,1fr) 56px;gap:0 26px;padding:34px 0 30px;border-bottom:1px solid var(--border);\n  opacity:0;transform:translateY(10px);animation:rise .55s cubic-bezier(.2,.7,.2,1) forwards;transition:background .3s}\n@keyframes rise{to{opacity:1;transform:none}}\n.tp .bit::before{content:\"\";position:absolute;left:-48px;top:0;bottom:0;width:2px;background:var(--dc);opacity:.0;transition:opacity .3s}\n.tp .bit.cur::before{opacity:1}\n.tp .bit[data-disp=\"act\"]{--dc:var(--act)}\n.tp .bit[data-disp=\"file\"]{--dc:var(--file)}\n.tp .bit[data-disp=\"archive\"]{--dc:var(--archive)}\n.tp .bit[data-disp=\"delete\"]{--dc:var(--delete)}\n.tp .bit[data-disp=\"merge\"]{--dc:var(--merge)}\n.tp .bit.rejected .said,.tp .bit.rejected .bt{opacity:.45;text-decoration:line-through;text-decoration-color:var(--delete);text-decoration-thickness:1px}\n.tp .bit .num{font-family:var(--font-display);font-size:30px;font-weight:300;color:var(--muted);line-height:1;padding-top:4px}\n.tp .bit .num i{display:block;font-style:normal;font-family:var(--font-mono);font-size:10px;letter-spacing:.12em;color:var(--muted);margin-top:10px}\n.tp .bit .num i::before{content:\"\";display:block;width:22px;height:1px;background:var(--dc);margin-bottom:8px}\n.tp .bit .num i.ec{margin-top:6px;color:var(--accent);text-transform:uppercase}\n.tp .bit .num i.ec::before{display:none}\n.tp .bt{font-family:var(--font-display);font-size:23px;font-weight:400;line-height:1.25;cursor:text;color:var(--text)}\n.tp .bt:hover{text-decoration:underline;text-decoration-color:color-mix(in oklab,var(--accent) 50%,transparent);text-underline-offset:6px;text-decoration-thickness:1px}\n.tp .bit input.bt{width:100%;border-bottom:1px solid var(--accent)}\n.tp .strip{display:flex;align-items:center;gap:14px;margin-top:12px}\n.tp .play{width:34px;height:34px;border-radius:50%;border:1px solid var(--border);display:grid;place-items:center;flex:none;transition:all .2s;color:var(--text)}\n.tp .play:hover{border-color:var(--accent);color:var(--accent)}\n.tp .play.on{border-color:var(--accent);background:var(--accent);color:var(--bg)}\n.tp .play svg{width:12px;height:12px;display:block}\n.tp .strip canvas{height:38px;width:100%;flex:1;display:block;cursor:pointer}\n.tp .strip .dur{font-family:var(--font-mono);font-size:10.5px;letter-spacing:.12em;color:var(--muted);flex:none}\n.tp .said{margin:18px 0 0;font-size:19px;line-height:1.6;font-weight:300;color:var(--ink);max-width:820px;text-wrap:pretty}\n.tp .said::before{content:\"\\201C\";color:var(--accent);margin-right:2px}\n.tp .said::after{content:\"\\201D\";color:var(--accent);margin-left:2px}\n.tp .ruling{margin-top:20px;display:flex;flex-wrap:wrap;align-items:baseline;gap:6px 0;font-family:var(--font-mono);font-size:12px;letter-spacing:.06em;color:var(--muted)}\n.tp .ruling .w{color:var(--text);padding:3px 6px;margin:0 -2px;border-radius:5px;transition:background .2s,color .2s;position:relative}\n.tp .ruling .w:hover,.tp .ruling .w.open{background:color-mix(in oklab,var(--accent) 16%,transparent);color:var(--accent)}\n.tp .ruling .w[data-f=\"disposition\"]{color:var(--dc)}\n.tp .ruling .w[data-f=\"category\"]{color:var(--accent)}\n.tp .ruling .sep{opacity:.5;padding:0 6px}\n.tp .ruling a.go{color:var(--accent);margin-left:12px;text-decoration:none;border-bottom:1px solid color-mix(in oklab,var(--accent) 40%,transparent);transition:border-color .2s}\n.tp .ruling a.go:hover{border-bottom-color:var(--accent)}\n.tp .ruling input{font-family:var(--font-mono);font-size:12px;color:var(--text);border-bottom:1px solid var(--border);padding:2px 4px;width:120px;margin-left:4px}\n.tp .ruling input[type=date]{color-scheme:dark;width:140px}\n.tp .gauges{display:flex;gap:28px;margin-top:16px;align-items:center;flex-wrap:wrap}\n.tp .gauge{display:flex;align-items:center;gap:10px}\n.tp .gauge span{font-family:var(--font-mono);font-size:10.5px;letter-spacing:.14em;text-transform:uppercase;color:var(--muted);width:82px}\n.tp .gauge .ticks{display:flex;gap:4px}\n.tp .gauge .tk{width:16px;height:8px;border-radius:2px;background:var(--border);transition:all .2s;border:0;padding:0}\n.tp .gauge .tk:hover{background:color-mix(in oklab,var(--accent) 50%,var(--border))}\n.tp .gauge .tk.on{background:var(--accent)}\n.tp .gauge[data-g=\"urgency\"] .tk.on{background:color-mix(in oklab,var(--accent) 60%,var(--delete))}\n.tp .next{margin-top:18px;display:grid;grid-template-columns:82px 1fr;gap:6px 10px;align-items:baseline;max-width:820px}\n.tp .next label{font-family:var(--font-mono);font-size:10.5px;letter-spacing:.14em;text-transform:uppercase;color:var(--muted)}\n.tp .next input,.tp .next textarea{width:100%;font-size:17px;line-height:1.45;border-bottom:1px solid var(--border);padding:2px 0;transition:border-color .2s;resize:vertical;min-height:0}\n.tp .next input:focus,.tp .next textarea:focus{border-bottom-color:var(--accent)}\n.tp .next input::placeholder,.tp .next textarea::placeholder{color:var(--muted);font-style:italic}\n.tp .cuts{margin-top:10px;display:flex;flex-wrap:wrap;gap:4px 14px;font-family:var(--font-mono);font-size:10.5px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted)}\n.tp .cuts a{color:var(--muted);text-decoration:none;border-bottom:1px solid transparent;transition:all .2s;cursor:pointer}\n.tp .cuts a:hover{color:var(--accent);border-bottom-color:var(--accent)}\n.tp .cuts a.rr{color:var(--accent)}\n.tp .cuts .busy{color:var(--accent);animation:tp-breathe 1.6s ease-in-out infinite}\n.tp .care{margin-top:12px;padding:8px 12px;border-left:2px solid color-mix(in oklab,var(--delete) 70%,var(--accent));background:color-mix(in oklab,var(--delete) 6%,transparent);font-size:13px;line-height:1.5}\n.tp .care.cleared{border-left-color:var(--border);background:none;color:var(--muted)}\n.tp .care .k{font-family:var(--font-mono);font-size:10px;letter-spacing:.14em;text-transform:uppercase;color:var(--accent);margin-right:8px}\n.tp .care.cleared .k{color:var(--muted)}\n.tp .care .cl{margin-left:10px;font-family:var(--font-mono);font-size:10px;letter-spacing:.12em;text-transform:uppercase;background:none;border:0;border-bottom:1px solid color-mix(in oklab,var(--accent) 40%,transparent);color:var(--text);cursor:pointer;padding:0}\n.tp .bit .num i.cm{margin-top:6px;color:var(--delete);text-transform:uppercase}\n.tp .brow .cm{color:var(--delete);font-family:var(--font-mono);font-size:10px;letter-spacing:.1em;text-transform:uppercase;margin-left:8px}\n.tp .rel{margin-top:10px;font-family:var(--font-mono);font-size:10.5px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted)}\n.tp .rel.fate{display:flex;gap:10px;align-items:center;flex-wrap:wrap}.tp .rel.fate b{font-weight:500;color:var(--ink,#EBEBE6)}.tp .rel.fate[data-w=court] b,.tp .rel.fate[data-w=held] b{color:#d9b38c}.tp .rel.fate[data-w=done] b,.tp .rel.fate[data-w=running] b{color:#9fc79a}\n.tp .rel a{margin-left:10px;text-decoration:none;border-bottom:1px solid color-mix(in oklab,var(--accent) 40%,transparent)}\n.tp .rel.disp{text-transform:none;letter-spacing:.06em}\n.tp .rel.disp[data-s=sent]{color:var(--ok)}\n.tp .rel.disp[data-s=failed]{color:var(--delete)}\n.tp .rel.disp[data-s=asks]{color:var(--accent)}\n.tp .rel.disp[data-s=answered]{color:var(--ok)}\n.tp .rel.disp[data-s=replied]{color:var(--muted)}\n.tp .ask{margin-top:12px;padding:14px 18px;border:1px solid color-mix(in oklab,var(--accent) 35%,var(--border));border-radius:12px;background:color-mix(in oklab,var(--accent) 5%,transparent)}\n.tp .ask .k{font-family:var(--font-mono);font-size:10.5px;letter-spacing:.12em;text-transform:uppercase;color:var(--accent)}\n.tp .ask .q{margin-top:6px;font-size:16px;line-height:1.5;color:var(--ink);white-space:pre-wrap;overflow-wrap:anywhere}\n.tp .ask .q a{overflow-wrap:anywhere}\n.tp .ask .q.dim{color:var(--muted);font-style:italic;white-space:normal}\n.tp .ask .reply{display:flex;gap:12px;align-items:center;margin-top:12px}\n.tp .ask .reply input{flex:1;min-width:0;font-family:var(--font-body);font-size:16px;line-height:1.45;border-bottom:1px solid var(--border);padding:3px 0;transition:border-color .2s}\n.tp .ask .reply input:focus{border-bottom-color:var(--accent)}\n.tp .ask .reply input::placeholder{color:var(--muted);font-style:italic}\n.tp .ask .reply button{font-family:var(--font-mono);font-size:11px;letter-spacing:.14em;text-transform:uppercase;padding:7px 14px;border:1px solid var(--border);border-radius:999px;transition:all .2s}\n.tp .ask .reply button:hover{border-color:var(--accent);color:var(--accent)}\n.tp .ask .reply button:disabled{opacity:.4;pointer-events:none}\n.tp .ask.busy{opacity:.5;pointer-events:none}\n.tp .ask .sent{margin-top:8px;font-size:14px;font-style:italic;color:var(--muted)}\n.tp .brow .ru .dsp[data-s=asks] a{color:var(--accent)}\n.tp .btot .needs{color:var(--accent)}\n.tp .brow .ru .dsp{margin-left:8px}\n.tp .brow .ru .dsp a{color:var(--ok);text-decoration:none}\n.tp .why{margin-top:8px;font-size:14px;font-style:italic;color:var(--muted)}\n.tp .seal{display:flex;flex-direction:column;align-items:center;gap:14px;padding-top:4px}\n.tp .seal button{width:40px;height:40px;border-radius:50%;border:1px solid var(--border);display:grid;place-items:center;transition:all .25s;color:var(--muted)}\n.tp .seal button svg{width:16px;height:16px}\n.tp .seal .ok:hover{border-color:var(--accent);color:var(--accent)}\n.tp .seal .ok.on{background:var(--accent);border-color:var(--accent);color:var(--bg);box-shadow:0 0 0 6px color-mix(in oklab,var(--accent) 18%,transparent)}\n.tp .seal .no:hover{border-color:var(--delete);color:var(--delete)}\n.tp .seal .no.on{background:var(--delete);border-color:var(--delete);color:var(--bg)}\n.tp .seal .conf{font-family:var(--font-mono);font-size:10px;letter-spacing:.1em;color:var(--muted)}\n.tp .seal .ed{font-family:var(--font-mono);font-size:9.5px;letter-spacing:.14em;text-transform:uppercase;color:var(--accent)}\n.tp .seal .auto{font-family:var(--font-mono);font-size:9.5px;letter-spacing:.14em;text-transform:uppercase;color:var(--accent);text-align:center;line-height:1.5}\n.tp .seal .auto.on{color:var(--muted);border:1px solid var(--border);border-radius:999px;padding:2px 7px}\n.tp .seal button.veto{width:auto;height:auto;border-radius:999px;padding:6px 11px;font-family:var(--font-mono);font-size:10px;letter-spacing:.14em;text-transform:uppercase;color:var(--delete);border-color:color-mix(in oklab,var(--delete) 55%,transparent)}\n.tp .seal button.veto:hover{background:var(--delete);color:var(--bg);border-color:var(--delete)}\n.tp .bit.auto-pending .seal .ok{border-style:dashed}\n.tp .meta .mode{color:var(--accent)}\n.tp .meta .mode[data-m=\"signoff\"]{color:var(--muted)}\n.tp .brow .st[data-s=\"auto-pending\"]{color:var(--accent)}\n.tp .brow .auto{font-size:9.5px;letter-spacing:.14em;text-transform:uppercase;color:var(--muted);border:1px solid var(--border);border-radius:999px;padding:1px 6px;margin-left:8px}\n@media (max-width:700px){.tp .bit{grid-template-columns:40px minmax(0,1fr)}\n.tp .seal{grid-column:1/-1;flex-direction:row;padding-top:14px}\n.tp .bit .num{font-size:22px}}\n.tp #pop{position:absolute;z-index:50;display:none;min-width:200px;max-width:360px;max-height:340px;overflow:auto;padding:6px;border-radius:12px;\n  background:color-mix(in oklab,var(--surface2) 96%,transparent);border:1px solid var(--border);box-shadow:0 30px 80px -30px #000,0 0 0 1px color-mix(in oklab,var(--accent) 10%,transparent);backdrop-filter:blur(12px)}\n.tp #pop button{display:block;width:100%;text-align:left;padding:7px 10px;border-radius:7px;font-family:var(--font-mono);font-size:12px;letter-spacing:.06em;color:var(--text);transition:background .15s}\n.tp #pop button small{display:block;font-family:var(--font-body);font-size:13px;letter-spacing:0;color:var(--muted);font-style:italic;line-height:1.3;margin-top:1px;text-transform:none}\n.tp #pop button:hover,.tp #pop button:focus{background:color-mix(in oklab,var(--accent) 16%,transparent);color:var(--accent);outline:0}\n.tp #pop button.cur{color:var(--accent)}\n.tp #pop button.cur::before{content:\"\\25CF\";margin-right:8px;font-size:8px;vertical-align:2px}\n.tp #board{margin-top:56px}\n.tp #board .hdr h2{cursor:default}\n.tp #board .hdr h2:hover{text-decoration:none}\n.tp .btot{margin-top:14px;font-family:var(--font-mono);font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted)}\n.tp .btot b{font-weight:400;color:var(--text)}\n.tp .bfilt{display:flex;flex-wrap:wrap;align-items:baseline;gap:10px 26px;margin-top:22px;font-family:var(--font-mono);font-size:12px;letter-spacing:.06em;color:var(--muted)}\n.tp .bfilt .grp{display:flex;align-items:baseline;flex-wrap:wrap;gap:0 2px}\n.tp .bfilt .grp>span{margin-right:8px}\n.tp .bfilt .w{color:var(--text);padding:3px 6px;margin:0 -2px;border-radius:5px;transition:background .2s,color .2s}\n.tp .bfilt .w:hover,.tp .bfilt .w.open{background:color-mix(in oklab,var(--accent) 16%,transparent);color:var(--accent)}\n.tp .bfilt input{width:240px;font-family:var(--font-body);font-size:17px;line-height:1.45;letter-spacing:0;border-bottom:1px solid var(--border);padding:2px 0;transition:border-color .2s}\n.tp .bfilt input:focus{border-bottom-color:var(--accent)}\n.tp .bfilt input::placeholder{color:var(--muted);font-style:italic}\n.tp .bgrp{margin-top:44px}\n.tp .bgrp .gh{display:flex;align-items:baseline;gap:18px;flex-wrap:wrap;padding-bottom:10px;border-bottom:1px solid var(--border)}\n.tp .bgrp .gh h3{margin:0;font-family:var(--font-display);font-weight:400;font-size:22px;color:var(--accent)}\n.tp .bgrp .gh .cnt{font-family:var(--font-mono);font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted)}\n.tp .bgrp .gh .gl{margin-left:auto;display:flex;gap:18px}\n.tp .brow{display:grid;grid-template-columns:6px minmax(0,1fr) auto auto auto;gap:0 18px;align-items:baseline;padding:12px 0;border-bottom:1px solid color-mix(in oklab,var(--border) 60%,transparent);transition:opacity .3s}\n.tp .brow.busy{opacity:.45;pointer-events:none}\n.tp .brow .dot{width:6px;height:6px;border-radius:50%;align-self:center;background:var(--file)}\n.tp .brow .ti{display:block;text-align:left;font-family:var(--font-display);font-size:17px;line-height:1.3;color:var(--text)}\n.tp .brow .ti:hover{text-decoration:underline;text-decoration-color:color-mix(in oklab,var(--accent) 50%,transparent);text-underline-offset:5px;text-decoration-thickness:1px}\n.tp .brow .ru,.tp .brow .dt,.tp .brow .st,.tp .brow .ops button{font-family:var(--font-mono);font-size:10.5px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted)}\n.tp .brow .ru{margin-top:4px}\n.tp .brow .st[data-s=\"signed\"]{color:var(--text)}\n.tp .brow .st[data-s=\"open\"]{color:var(--accent)}\n.tp .brow .st[data-s=\"done\"]{color:var(--ok)}\n.tp .brow .st[data-s=\"dropped\"],.tp .brow .st[data-s=\"rejected\"]{color:var(--delete)}\n.tp .brow .st[data-s=\"filed\"]{color:var(--file)}\n.tp .brow .ops{display:flex;gap:12px;min-width:90px;justify-content:flex-end}\n.tp .brow .ops button{border-bottom:1px solid transparent;transition:color .2s,border-color .2s}\n.tp .brow .ops button:hover{color:var(--accent);border-bottom-color:var(--accent)}\n@media (max-width:700px){.tp .brow{grid-template-columns:6px minmax(0,1fr) auto auto}\n.tp .brow .dt{display:none}}\n.tp footer{margin-top:80px;font-family:var(--font-mono);font-size:10.5px;letter-spacing:.14em;text-transform:uppercase;color:var(--muted);line-height:2}\n.tp footer b{font-weight:400;color:var(--text)}\n.tp kbd{font-family:var(--font-mono);font-size:10px;border:1px solid var(--border);border-radius:4px;padding:1px 5px;color:var(--text)}\n@media (prefers-reduced-motion:reduce){.tp *{animation:none!important;transition:none!important}\n.tp .bit{opacity:1;transform:none}}\n\n"

export const TAPE_HTML = "<div id=\"status\"><span></span></div>\n<div id=\"app\">\n  <aside id=\"shelf\">\n    <h1>memos <span class=\"views\"><button data-v=\"tape\" class=\"on\" title=\"the selected memo, bit by bit\">tape</button><button data-v=\"board\" title=\"every bit across every memo\">board</button></span></h1>\n    <div id=\"list\"></div>\n  </aside>\n  <main id=\"main\">\n    <section id=\"plate\">\n      <div class=\"ring\"><i></i></div>\n      <h2>Speak. <em>It becomes decisions.</em></h2>\n      <p>Press record and talk, drop a voice memo anywhere on this page, or write. The tape is cut where you pause, each thought gets a ruling, and you sign.</p>\n      <div id=\"talk\">\n        <button id=\"recBtn\" aria-label=\"talk through: tap to record, tap again to stop\" title=\"talk through: tap to record, tap again to stop\"></button>\n        <div class=\"tk\"><b>Talk through. <em>The cuts are made for you.</em></b><span id=\"recClock\">00:00</span>\n          <canvas id=\"recLvl\" height=\"28\"></canvas><span class=\"mono\" id=\"recNote\">tap to record &middot; tap again to stop &middot; it goes to the box while you talk</span></div>\n      </div>\n      <div class=\"ways\">\n        <button class=\"lnk\" id=\"choose\">choose a recording</button>\n        <input id=\"file\" type=\"file\" multiple accept=\"audio/*,video/*\" hidden>\n        <button class=\"lnk\" id=\"writeToggle\">write instead</button>\n        <span class=\"mono\" id=\"plateInfo\"></span>\n      </div>\n      <div class=\"words\">\n        <textarea id=\"txt\" placeholder=\"a thought, as it comes\"></textarea>\n        <div class=\"ways\"><button class=\"lnk\" id=\"take\">take as memo</button><span class=\"mono\" id=\"txtres\"></span></div>\n      </div>\n      <div id=\"progs\"></div>\n    </section>\n    <section id=\"memo\"></section>\n    <section id=\"board\" style=\"display:none\"></section>\n    <footer>memos live in <b id=\"tpDir\"></b> &middot; the watcher takes new ones every few minutes<br>\n      <kbd>j</kbd> <kbd>k</kbd> move &middot; <kbd>space</kbd> play &middot; <kbd>a</kbd> approve &middot; <kbd>r</kbd> reject &middot; <kbd>v</kbd> veto (auto mode) &middot; <kbd>s</kbd> save</footer>\n  </main>\n</div>\n<div id=\"pop\" role=\"menu\"></div>\n<audio id=\"deck\" preload=\"none\"></audio>"

export function mountTape(root, opts) {
  opts = opts || {}
  root.innerHTML = TAPE_HTML
  var offs = [], timers = []
  var on = function (t, type, fn, o) { t.addEventListener(type, fn, o); offs.push(function () { t.removeEventListener(type, fn, o) }) }
  var every = function (fn, ms) { var id = setInterval(fn, ms); timers.push(id); return id }
  var R = null, S = null
  try {
var DEMO=!!opts.demo;
var MEMOS=opts.dir||'/tape', INBOX=MEMOS+'/inbox', SIGNER=opts.signer||'owner', WORLD=opts.world||'';
var RAW=function(p){return '/cc/tape/file?path='+encodeURIComponent(p);};
var LIST=function(p){return '/cc/tape/stat?path='+encodeURIComponent(p);};
var $=function(s,r){return (r||root).querySelector(s);};
var $$=function(s){return root.querySelectorAll(s);};
var el=function(tag,attrs,kids){var e=document.createElement(tag);if(attrs)Object.keys(attrs).forEach(function(k){
  if(k==='text')e.textContent=attrs[k];else if(k==='html')e.innerHTML=attrs[k];else if(k==='cls')e.className=attrs[k];
  else if(k.slice(0,2)==='on')e.addEventListener(k.slice(2),attrs[k]);else if(attrs[k]!=null)e.setAttribute(k,attrs[k]);});
  (kids||[]).forEach(function(c){if(c==null)return;e.appendChild(typeof c==='string'?document.createTextNode(c):c);});return e;};
var FIELDS=['category','kind','act_when','who','effort','output','disposition'];
var WORKING={'new':1,transcribing:1,deciding:1};
var S={index:null,vocab:null,id:null,doc:null,wave:null,mtime:null,dirty:false,saving:false,cur:-1,timer:null,popFor:null,playing:-1,stopAt:null,
  view:'tape',board:null,boardErr:false,boardTimer:null,bf:null};
var CSS=getComputedStyle(document.documentElement);
var C=function(v){return CSS.getPropertyValue(v).trim();};
var DISPC={act:C('--accent'),file:C('--file'),archive:C('--archive'),delete:C('--delete'),merge:C('--merge')};


/* status */
var statusEl=$('#status'),statusT=null;
function status(msg,kind){var sp=$('span',statusEl);sp.textContent=msg||'';statusEl.className=(msg?'show ':'')+(kind||'');clearTimeout(statusT);
  if(msg&&kind!=='err')statusT=setTimeout(function(){statusEl.className='';},5000);}

function getJSON(url){return fetch(url,{credentials:'same-origin',cache:'no-store'}).then(function(r){if(!r.ok)throw new Error(r.status+' '+url);return r.json();});}
function listing(p){return getJSON(LIST(p));}
function writeText(p,text,mtime){if(DEMO)return Promise.resolve({ok:true,mtime:Date.now()/1000|0});var body={path:p,text:text};if(mtime!=null)body.mtime=mtime;
  return fetch('/cc/tape/write',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})
  .then(function(r){return r.json().catch(function(){return {ok:false,error:'bad response '+r.status};}).then(function(j){j._status=r.status;return j;});});}
function mmss(s){if(s==null||isNaN(s))return '--:--';s=Math.round(s);var m=Math.floor(s/60),x=s%60;return (m<10?'0':'')+m+':'+(x<10?'0':'')+x;}
function fmtDate(iso){if(!iso)return '';var d=new Date(iso);if(isNaN(d))return String(iso).slice(0,16);var p=function(n){return (n<10?'0':'')+n;};
  return d.getFullYear()+'-'+p(d.getMonth()+1)+'-'+p(d.getDate())+' '+p(d.getHours())+':'+p(d.getMinutes());}
function nowIso(){return new Date().toISOString();}
function unsigned(b){var so=b.signoff||'pending';return so==='pending'||so==='auto-pending';}
function pending(doc){return (doc&&doc.bits||[]).filter(unsigned).length;}
/* sign-off as a veto (2026-10-25, D73): a memo created after the ruling is auto mode; the pipeline says which in index.json */
function memoMode(d){var ix=indexEntry(d.id)||{};return ix.mode||d.signoff_mode||'signoff';}
function autoLeft(b){if(!b.auto_at)return null;var t=new Date(b.auto_at);if(isNaN(t))return null;return Math.max(0,Math.ceil((t-Date.now())/60000));}
function veto(i){var b=S.doc&&S.doc.bits[i];if(!b||(b.signoff||'pending')!=='auto-pending')return;b.signoff='rejected';b.signoff_by=SIGNER;b.vetoed_at=nowIso();markDirty();rerenderBit(i);status('vetoed: this bit is let go and is never auto-approved','ok');}
function esc(s){return String(s).replace(/[&<>"]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];});}
function dpr(cv){var r=window.devicePixelRatio||1,w=cv.clientWidth||300,h=cv.clientHeight||40;cv.width=w*r;cv.height=h*r;var g=cv.getContext('2d');g.setTransform(r,0,0,r,0,0);return {g:g,w:w,h:h};}

/* ---------- demo data (for design checks with ?demo=1) ---------- */
function demoWave(n,seed){var out=[],x=seed||7;for(var i=0;i<n;i++){x=(x*16807)%2147483647;var env=.35+.65*Math.abs(Math.sin(i/37))*(0.5+0.5*Math.sin(i/9+x%3));var v=(x/2147483647)*env;if(i%97<9)v*=.08;out.push(+v.toFixed(3));}return out;}
var DEMO_BITS=[
 {n:1,title:'Record memos from the phone straight to the box',start:0,end:41,text:'I want to talk into the phone on a walk and have it land on the box without sending files around.',category:'work',kind:'task',act_when:'this-week',importance:4,urgency:3,who:'agent',effort:'hours',output:'code',disposition:'act',next_step:'Put a record button on the tape page that uploads while I talk.',confidence:.9,why:'a build request with a clear owner',signoff:'approved',relates_to:[]},
 {n:2,title:'Cut long talks where I pause',start:41,end:88,text:'When I talk for twenty minutes it should come back as separate thoughts, cut where I stop to think.',category:'work',kind:'task',act_when:'this-week',importance:4,urgency:3,who:'agent',effort:'days',output:'code',disposition:'act',next_step:'Split the transcript at pauses longer than a second.',confidence:.9,signoff:'pending',relates_to:[1],echoes:[{memo:'2026-10-10_1830_demo-b',n:2,title:'Cut the tape where the voice pauses',score:.82}]},
 {n:3,title:'Speaking is faster than typing',start:88,end:101,text:'Speaking is just faster than typing for me.',category:'work',kind:'reflection',act_when:'never',importance:2,urgency:1,who:'me',effort:'minutes',output:'none',disposition:'file',next_step:'none',confidence:.8,signoff:'pending',relates_to:[]},
 {n:4,title:'Do it with video too',start:101,end:109,text:'Maybe later the same for short videos.',category:'work',kind:'idea',act_when:'someday',importance:2,urgency:1,who:'agent',effort:'days',output:'code',disposition:'archive',next_step:'none',confidence:.75,signoff:'rejected',relates_to:[]},
 {n:5,title:'Plan the garden before spring',start:109,end:150,text:'And I need to sit down and plan the garden before spring, what goes where.',category:'home',kind:'plan',act_when:'this-month',importance:3,urgency:2,who:'me',effort:'hours',output:'plan',disposition:'act',next_step:'Sketch the beds and list the seeds to order.',confidence:.85,signoff:'pending',relates_to:[],care:[{flag:'argue',why:'Planning everything at once has stalled before; one bed first would land sooner.'}],care_state:'open',private:true}];
var DEMO_DOC={id:'2026-10-11_1251_demo',created:'2026-10-11T12:51:56Z',stage:'decided',language:'en',title:'A record button for walks',
  summary:'A memo asking for a way to talk on the phone and have the take land on the box, cut into thoughts at the pauses, with a note about the garden at the end.',
  themes:['voice intake','cutting','garden'],source:{name:'memo-demo.m4a',kind:'audio',duration:150,path:'/x'},bits:DEMO_BITS,review:{done:false},filed:null};
var DEMO_INDEX={memos:[{id:DEMO_DOC.id,title:DEMO_DOC.title,created:DEMO_DOC.created,stage:'decided',duration:150,n_bits:5,n_pending:3,mini:demoWave(64,3)},
  {id:'2026-10-10_1830_demo-b',title:'Notes after the call',created:'2026-10-10T18:30:00Z',stage:'filed',duration:62,n_bits:3,n_pending:0,mini:demoWave(64,11),filed:{note:'memos/demo-b.md'}},
  {id:'2026-10-10_0915_demo-c',title:'Morning walk',created:'2026-10-10T09:15:00Z',stage:'transcribing',duration:214,n_bits:0,n_pending:0,mini:[]}]};

/* ---------- vocab + index ---------- */
function loadVocab(){return (DEMO?Promise.reject(new Error('demo')):(opts.vocab?getJSON('/cc/tape/file?path=vocab.json'):Promise.reject(new Error('no vocab.json on the tape')))).then(function(v){S.vocab=v;}).catch(function(e){
  S.vocab={category:['work','home','people','music','writing','other'],kind:['idea','task','decision','question','lyric','reflection','reminder','fact','plan'],act_when:['now','today','this-week','this-month','date','someday','never'],who:['agent','me','me+agent','other'],effort:['minutes','hours','days','weeks'],output:['essay','video','track','code','note','decision','message','research','plan','design','none'],disposition:['act','file','archive','delete','merge'],signoff:['pending','approved','rejected'],category_hint:{}};
  if(!DEMO&&opts.vocab)status('vocab.json not readable ('+e.message+'); using a minimal fallback','err');});}
function loadIndex(){if(DEMO){S.index=DEMO_INDEX;renderList();return Promise.resolve();}
  return getJSON(RAW(MEMOS+'/index.json')).then(function(ix){S.index=ix;renderList();})
  .catch(function(e){if(!S.index){S.index={memos:[]};renderList();}status('index.json: '+e.message,'err');});}
function indexEntry(id){return (S.index&&S.index.memos||[]).filter(function(m){return m.id===id;})[0]||null;}

function renderList(){var box=$('#list');box.innerHTML='';
  var ms=(S.index&&S.index.memos||[]).slice().sort(function(a,b){return String(b.created||'').localeCompare(String(a.created||''));});
  $('#plateInfo').textContent=ms.length?ms.length+' memo'+(ms.length>1?'s':'')+' on the tape':'';
  if(!ms.length){box.appendChild(el('div',{cls:'empty',text:'nothing on the tape yet'}));return;}
  ms.forEach(function(m){var st=m.stage||'new';var pc='pip '+(st==='filed'?'filed':st==='error'?'error':st==='decided'?'decided':WORKING[st]?'working':'');
    var cv=el('canvas',{title:'click to open this memo and play from here'});
    cv.addEventListener('click',function(e){e.stopPropagation();var r=cv.getBoundingClientRect();var f=(e.clientX-r.left)/r.width;setView('tape');
      select(m.id).then(function(){var dur=(S.doc&&S.doc.source&&S.doc.source.duration)||m.duration||0;var k=nearestBit(f*dur);if(k>=0){var b=S.doc.bits[k];setCur(k,true);playBit(k,Math.min(Math.max(f*dur,b.start),b.end-0.2));}});});
    var b=el('button',{cls:'mi'+(m.id===S.id?' sel':''),onclick:function(){setView('tape');select(m.id);}},[
      el('span',{cls:'t',text:m.title||m.id}),
      el('span',{cls:'m'},[el('span',{html:'<i class="'+pc+'"></i>'+esc(st)}),el('span',{text:mmss(m.duration)}),el('span',{text:m.n_pending?m.n_pending+' pending':(m.n_bits?m.n_bits+' bits':'')})]),cv]);
    box.appendChild(b);requestAnimationFrame(function(){drawMini(cv,m.mini||[],m.id===S.id);});});}
function drawMini(cv,mini,sel){var o=dpr(cv),g=o.g,w=o.w,h=o.h;g.clearRect(0,0,w,h);if(!mini.length){g.fillStyle=C('--border');g.fillRect(0,h/2,w,1);return;}
  var n=mini.length,bw=w/n;g.fillStyle=sel?C('--accent'):C('--muted');for(var i=0;i<n;i++){var v=Math.max(.05,mini[i])*h*.95;g.fillRect(i*bw+bw*.25,(h-v)/2,Math.max(1,bw*.5),v);}}

/* ---------- selected memo ---------- */
function bitsPath(id){return MEMOS+'/'+id+'/bits.json';}
function select(id,keep){if(S.dirty&&S.id&&S.id!==id&&!confirm('unsaved edits on '+S.id+'; discard?'))return Promise.resolve();
  stopPlay();S.id=id;S.dirty=false;clearTimeout(S.timer);if(!keep)S.cur=-1;closePop();renderList();
  if(DEMO){S.doc=JSON.parse(JSON.stringify(DEMO_DOC));S.doc.id=id;S.wave={duration:150,peak:demoWave(1600,5)};renderMemo();return Promise.resolve();}
  var mt=null;return listing(bitsPath(id)).then(function(l){mt=l&&l.mtime!=null?l.mtime:null;return getJSON(RAW(bitsPath(id)));})
  .then(function(doc){S.doc=doc;S.mtime=mt;S.wave=null;renderMemo();
    return getJSON(RAW(MEMOS+'/'+id+'/waveform.json')).then(function(w){if(S.id===id){S.wave=w;drawTape();rerenderStrips();}}).catch(function(){});})
  .catch(function(e){S.doc=null;var ix=indexEntry(id);var box=$('#memo');box.innerHTML='';
    box.appendChild(el('div',{cls:'hdr'},[el('div',{cls:'kicker mono',text:id}),el('h2',{text:ix&&ix.title||id})]));
    if(ix&&WORKING[ix.stage])box.appendChild(el('div',{cls:'working',html:'<i></i>'+esc(ix.stage)+' &middot; this page refreshes by itself'}));
    else box.appendChild(el('div',{cls:'errbox',text:(ix&&ix.error)||('no bits.json yet: '+e.message)}));});}

function markDirty(){S.dirty=true;clearTimeout(S.timer);S.timer=setTimeout(function(){save();},1500);updateBar();}
function setField(b,k,v){if(b[k]===v)return;b[k]=v;b.edited=true;markDirty();}

function renderMemo(){var d=S.doc,box=$('#memo');box.innerHTML='';if(!d)return;
  var ix=indexEntry(d.id)||{};var stage=d.stage||ix.stage||'new';var src=d.source||{};
  var h2=el('h2',{text:d.title||d.id,title:'click to rename'});
  h2.addEventListener('click',function(){var inp=el('input',{value:d.title||''});h2.replaceWith(inp);inp.focus();
    var done=function(ok){if(ok&&inp.value.trim()!==(d.title||'')){d.title=inp.value.trim();markDirty();}h2.textContent=d.title||d.id;inp.replaceWith(h2);};
    inp.addEventListener('keydown',function(e){if(e.key==='Enter')done(true);if(e.key==='Escape')done(false);});inp.addEventListener('blur',function(){done(true);});});
  box.appendChild(el('div',{cls:'hdr'},[el('div',{cls:'kicker mono',text:'memo · '+fmtDate(d.created)}),h2]));
  box.appendChild(el('div',{cls:'meta'},[el('span',{cls:'stage',text:stage}),el('span',{text:mmss(src.duration!=null?src.duration:ix.duration)}),
    el('span',{text:d.language||ix.language||''}),el('span',{text:src.name||''}),el('span',{text:(d.bits||[]).length+' bits'}),
    el('span',{cls:'mode','data-m':memoMode(d),text:memoMode(d)==='auto'?'auto mode':'sign-off mode',title:memoMode(d)==='auto'?'ruled bits approve themselves after the veto window unless you veto; approve and reject still rule':'its bits move only after you sign them and press done, file it'})]));
  if(stage==='error'||d.error)box.appendChild(el('div',{cls:'errbox',text:d.error||ix.error||'error'}));
  if(WORKING[stage])box.appendChild(el('div',{cls:'working',html:'<i></i>'+esc(stage)+' &middot; this page refreshes by itself'}));
  if(d.summary)box.appendChild(el('p',{cls:'summary',text:d.summary}));
  if(d.themes&&d.themes.length)box.appendChild(el('div',{cls:'themes'},d.themes.map(function(t){return el('span',{text:t});})));
  if(src.kind!=='text'&&(d.bits||[]).length){var tape=el('div',{id:'tape'},[el('canvas'),el('div',{cls:'head'})]);box.appendChild(tape);
    box.appendChild(el('div',{cls:'tape-note'},['act','file','archive','delete','merge'].map(function(k){return el('span',{html:'<i class="sw" style="background:'+DISPC[k]+'"></i>'+k});}).concat([el('span',{html:'<b>'+mmss(src.duration)+'</b> of your voice, cut where you paused'})])));
    tape.addEventListener('click',function(e){var r=tape.getBoundingClientRect();var t=(e.clientX-r.left)/r.width*(S.wave&&S.wave.duration||src.duration||1);var k=nearestBit(t);if(k>=0){var b=S.doc.bits[k];setCur(k,true);playBit(k,Math.min(Math.max(t,b.start),b.end-0.2));}});
    tape.addEventListener('mousemove',function(e){var r=tape.getBoundingClientRect();var t=(e.clientX-r.left)/r.width*(S.wave&&S.wave.duration||src.duration||1);var k=bitAt(t);
      Array.prototype.forEach.call(tape.querySelectorAll('.lab'),function(l,i){l.classList.toggle('on',i===k);});});}
  var bar=el('div',{cls:'bar',id:'bar'});box.appendChild(bar);
  box.appendChild(el('div',{cls:'next',id:'next'}));
  box.appendChild(el('div',{cls:'mono barnote',text:'a seal means the ruling is right, not that the work is done; done lives on the board'}));
  var holder=el('div',{id:'bits'});box.appendChild(holder);
  var bits=d.bits||[];
  if(!bits.length)holder.appendChild(el('div',{cls:'empty',text:WORKING[stage]?'the bits appear once deciding finishes':'nothing was heard'}));
  bits.forEach(function(b,i){holder.appendChild(renderBit(b,i));});
  updateBar();drawTape();}

function bitAt(t){var bs=S.doc&&S.doc.bits||[];for(var i=0;i<bs.length;i++){if(bs[i].start!=null&&t>=bs[i].start&&t<=bs[i].end)return i;}return -1;}
function nearestBit(t){var k=bitAt(t);if(k>=0)return k;var bs=S.doc&&S.doc.bits||[],best=-1,d=1e9;bs.forEach(function(b,i){if(b.start==null)return;var dd=t<b.start?b.start-t:t-b.end;if(dd<d){d=dd;best=i;}});return best;}

/* the tape: one waveform, bits as lit spans */
function drawTape(){var tape=$('#tape');if(!tape||!S.doc)return;var cv=$('canvas',tape);var o=dpr(cv),g=o.g,w=o.w,h=o.h;g.clearRect(0,0,w,h);
  var d=S.doc,dur=(S.wave&&S.wave.duration)||(d.source&&d.source.duration)||1,pk=S.wave&&S.wave.peak||[];
  var top=18,base=h-22,mid=top+(base-top)/2,amp=(base-top)/2;
  // spans first
  var bits=d.bits||[];bits.forEach(function(b,i){if(b.start==null)return;var x0=b.start/dur*w,x1=b.end/dur*w;var col=DISPC[b.disposition]||DISPC.file;
    g.fillStyle=col;g.globalAlpha=(i===S.playing?.32:i===S.cur?.22:.09);g.fillRect(x0,top-6,x1-x0,base-top+12);g.globalAlpha=1;
    g.fillStyle=col;g.fillRect(x0,base+6,Math.max(1,x1-x0-1),2);});
  // waveform
  if(pk.length){var n=pk.length,bw=w/n;for(var i=0;i<n;i++){var t=i/n*dur,k=bitAt(t);var b=k>=0?bits[k]:null;var col=b?(DISPC[b.disposition]||DISPC.file):C('--muted');
      var v=Math.max(.02,pk[i])*amp;g.fillStyle=col;g.globalAlpha=b?(b.signoff==='rejected'?.3:(k===S.cur?1:.8)):.35;g.fillRect(i*bw,mid-v,Math.max(.8,bw*.72),v*2);}g.globalAlpha=1;}
  else{g.fillStyle=C('--border');g.fillRect(0,mid,w,1);}
  // labels + times
  Array.prototype.forEach.call(tape.querySelectorAll('.lab,.time'),function(e){e.remove();});
  bits.forEach(function(b,i){if(b.start==null)return;var lab=el('div',{cls:'lab'+(i===S.cur?' on':''),text:(b.n||i+1)+' · '+(b.title||'')});lab.style.left=(b.start/dur*100)+'%';
    lab.style.maxWidth=Math.max(40,(b.end-b.start)/dur*w-6)+'px';lab.style.overflow='hidden';lab.style.textOverflow='ellipsis';tape.appendChild(lab);});
  [0,.25,.5,.75,1].forEach(function(f){var t=el('div',{cls:'time',text:mmss(f*dur)});t.style.left=(f*100)+'%';if(f===1)t.style.transform='translateX(-100%)';else if(f>0)t.style.transform='translateX(-50%)';tape.appendChild(t);});}

/* one line under the bar: what is happening, what you must do, what happens after */
function nextText(d){var ix=indexEntry(d.id)||{};var stage=d.stage||ix.stage||'new';var np=pending(d),done=d.review&&d.review.done,filed=d.filed||ix.filed;
  var bits=d.bits||[],na=bits.filter(function(b){return b.signoff==='approved';}).length,nact=bits.filter(function(b){return b.signoff==='approved'&&b.disposition==='act';}).length;
  if(stage==='error'||d.error)return '<b>stopped.</b> the error is above. nothing moves until it is cleared; retry with memo.py advance from the terminal.';
  if(stage==='new'||stage==='transcribing')return '<b>transcribing</b> on the box, about a third of real time. then the reasoner cuts it into bits. nothing for you to do yet.';
  if(stage==='transcribed'||stage==='deciding')return '<b>deciding:</b> the reasoner groups the words into bits and rules on each. they appear here with clips. nothing for you to do yet.';
  if(filed){var open=bits.filter(function(b){return b.signoff==='approved'&&b.disposition==='act'&&(b.status||'open')==='open';}).length;
    return '<b>filed</b>. '+nact+' act bit'+(nact===1?'':'s')+' on the queue, '+open+' still open. nothing moves by itself: an agent or you takes a row, then mark it done or dropped on the board.';}
  if(done)return '<b>filing</b> within two minutes: a note with the '+na+' approved bits, '+nact+' act bit'+(nact===1?'':'s')+' onto the queue.';
  if(memoMode(d)==='auto'){var armed=bits.filter(function(b){return b.signoff==='auto-pending';}),mins=armed.map(autoLeft).filter(function(m){return m!=null;});
    if(armed.length)return '<b>auto mode:</b> '+armed.length+' bit'+(armed.length===1?'':'s')+' approve'+(armed.length===1?'s itself':' themselves')+(mins.length?' in '+Math.min.apply(null,mins)+' min':'')+' unless you veto; approve or reject still rule. filing and dispatch follow by themselves.';
    if(np>0)return '<b>auto mode:</b> '+np+' bit'+(np===1?'':'s')+' not yet ruled; the watcher arms each ruled bit with a '+'veto window within two minutes.';
    if(bits.length)return '<b>every bit has a verdict.</b> auto mode: the memo files itself within two minutes; done, file it is optional.';}
  if(np>0)return '<b>'+np+' bit'+(np===1?' needs':'s need')+' your verdict:</b> approve or reject each (approving fixes the ruling, not the work). nothing is written until every bit has one and you press done, file it.';
  if(!bits.length)return 'nothing was heard in this memo. nothing to file.';
  return '<b>every bit has a verdict.</b> press <b>done, file it</b>: the '+na+' approved are filed as a note, the '+nact+' marked act go onto the queue. until then nothing is written anywhere.';}

function updateBar(){var bar=$('#bar'),d=S.doc;if(!bar||!d)return;bar.innerHTML='';
  var np=pending(d),done=d.review&&d.review.done,filed=d.filed||(indexEntry(d.id)||{}).filed,na=(d.bits||[]).filter(function(b){return b.signoff==='approved';}).length;
  bar.appendChild(el('button',{cls:'act',text:'approve all pending',disabled:np?null:'',onclick:function(){(d.bits||[]).forEach(function(b){if(unsigned(b)){b.signoff='approved';b.signoff_by=SIGNER;}});markDirty();rerenderAll();}}));
  bar.appendChild(el('button',{cls:'act'+(S.dirty?' gold':''),text:S.saving?'saving':S.dirty?'save':'saved',disabled:S.dirty&&!S.saving?null:'',onclick:function(){save();}}));
  bar.appendChild(el('button',{cls:'act'+(np===0&&!done&&(d.bits||[]).length?' gold':''),text:done?'review done':'done, file it',disabled:(np===0&&!done&&(d.bits||[]).length)?null:'',title:np?np+' still pending':'',onclick:doneFile}));
  var info=el('span',{cls:'info',html:'<b>'+(d.bits||[]).length+'</b> bits &middot; <b>'+np+'</b> pending &middot; <b>'+na+'</b> approved'});
  if(done&&!filed)info.innerHTML+=' &middot; <b>done</b>, filing within two minutes';
  bar.appendChild(info);
  if(filed)bar.appendChild(el('span',{cls:'info filed',text:'filed '+(filed.note||'')+(filed.commit?' · '+String(filed.commit).slice(0,7):'')}));
  var nx=$('#next');if(nx)nx.innerHTML=nextText(d);}

function rerenderAll(){var holder=$('#bits');if(!holder||!S.doc)return;holder.innerHTML='';(S.doc.bits||[]).forEach(function(b,i){holder.appendChild(renderBit(b,i));});drawTape();}
function rerenderBit(i){var old=$('#bits').children[i];if(!old)return rerenderAll();var n=renderBit(S.doc.bits[i],i);n.style.animation='none';n.style.opacity=1;n.style.transform='none';old.replaceWith(n);updateBar();drawTape();}
function rerenderStrips(){Array.prototype.forEach.call($$('.strip canvas'),function(cv){drawStrip(cv,S.doc.bits[+cv.getAttribute('data-i')],+cv.getAttribute('data-i'));});}

var ICON_PLAY='<svg viewBox="0 0 12 12"><path d="M2 1l9 5-9 5z" fill="currentColor"/></svg>',ICON_STOP='<svg viewBox="0 0 12 12"><rect x="2" y="2" width="8" height="8" fill="currentColor"/></svg>';
var ICON_OK='<svg viewBox="0 0 16 16"><path d="M3 8.5l3.2 3L13 4.5" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>';
var ICON_NO='<svg viewBox="0 0 16 16"><path d="M4 4l8 8M12 4l-8 8" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>';

var CARE_LABEL={person:'a person','sz-legal':'sz or legal','may-be-wrong':'may be wrong',controversial:'controversial',wellbeing:'your wellbeing',argue:'I would argue against'};
function careOpen(b){return !!(b.care&&b.care.length&&b.care_state==='open');}
/* care marks: the brain's quiet second reading; clearing keeps the words and the mark, it only says "seen" */
function careBlock(b,i){if(!b.care||!b.care.length)return null;var open=b.care_state==='open';var box=el('div',{cls:'care'+(open?'':' cleared')});
  b.care.forEach(function(c,k){var line=el('div',{},[el('span',{cls:'k',text:CARE_LABEL[c.flag]||c.flag}),el('span',{text:c.why||''})]);
    if(k===b.care.length-1){line.appendChild(el('button',{cls:'cl',text:open?'clear':'cleared · undo',title:open?'seen; the mark stays on record, the bit stays private and may be dispatched':'open the mark again',onclick:function(e){e.stopPropagation();
      if(open){b.care_state='cleared';b.care_cleared=b.care.map(function(z){return z.flag;});}else{b.care_state='open';b.care_cleared=[];}markDirty();rerenderBit(i);drawTape&&drawTape();}}));}
    box.appendChild(line);});
  if(b.private)box.appendChild(el('div',{cls:'k',text:'private'}));return box;}
function renderBit(b,i){var d=S.doc;var so=b.signoff||'pending';var disp=b.disposition||'file';
  var card=el('article',{cls:'bit '+so+(i===S.cur?' cur':''),'data-disp':disp,'data-i':i,id:'bit-'+b.n});card.style.animationDelay=(Math.min(i,12)*45)+'ms';
  card.addEventListener('mousedown',function(){setCur(i,false);});
  card.appendChild(el('div',{cls:'num',html:(b.n!=null?b.n:i+1)+'<i>'+(b.start!=null?mmss(b.start):'')+'</i>'+(b.echoes&&b.echoes.length?'<i class="ec" title="the same thought, said in other memos too">said '+(b.echoes.length+1)+'x</i>':'')+(careOpen(b)?'<i class="cm" title="a care mark: worth a look before it goes anywhere">look</i>':'')}));
  var body=el('div');card.appendChild(body);
  var tt=el('div',{cls:'bt',text:b.title||'(untitled)',title:'click to retitle'});
  tt.addEventListener('click',function(){var inp=el('input',{cls:'bt',value:b.title||''});tt.replaceWith(inp);inp.focus();
    var done=function(ok){if(ok&&inp.value.trim()!==(b.title||''))setField(b,'title',inp.value.trim());tt.textContent=b.title||'(untitled)';inp.replaceWith(tt);drawTape();};
    inp.addEventListener('keydown',function(e){if(e.key==='Enter')done(true);if(e.key==='Escape')done(false);});inp.addEventListener('blur',function(){done(true);});});
  body.appendChild(tt);
  if(d.source&&d.source.kind!=='text'&&b.start!=null){var pb=el('button',{cls:'play'+(S.playing===i?' on':''),html:S.playing===i?ICON_STOP:ICON_PLAY,title:'play this bit',onclick:function(e){e.stopPropagation();if(S.playing===i)stopPlay();else playBit(i);}});
    var cv=el('canvas',{'data-i':i});cv.addEventListener('click',function(e){var r=cv.getBoundingClientRect();playBit(i,b.start+(e.clientX-r.left)/r.width*(b.end-b.start));});
    body.appendChild(el('div',{cls:'strip'},[pb,cv,el('span',{cls:'dur',text:mmss(b.start)+' – '+mmss(b.end)})]));requestAnimationFrame(function(){drawStrip(cv,b,i);});}
  body.appendChild(el('p',{cls:'said',text:b.text||''}));
  // the ruling: a sentence of choices
  var ru=el('div',{cls:'ruling'});
  var word=function(f,label){var w=el('button',{cls:'w','data-f':f,text:label||b[f]||'—',title:f.replace('_',' ')});w.addEventListener('click',function(e){e.stopPropagation();openPop(w,f,b[f],function(v){setField(b,f,v);rerenderBit(i);});});return w;};
  var sep=function(t){return el('span',{cls:'sep',text:t||'·'});};
  ru.appendChild(word('category'));ru.appendChild(sep());ru.appendChild(word('kind'));ru.appendChild(sep());
  ru.appendChild(el('span',{text:'when '}));ru.appendChild(word('act_when'));
  if(b.act_when==='date'){var di=el('input',{type:'date',value:b.act_date||''});di.addEventListener('change',function(){setField(b,'act_date',di.value||null);});ru.appendChild(di);}
  ru.appendChild(sep());ru.appendChild(el('span',{text:'who '}));ru.appendChild(word('who'));
  if(b.who==='other'){var wi=el('input',{placeholder:'name',value:b.who_name||''});wi.addEventListener('input',function(){setField(b,'who_name',wi.value||null);});ru.appendChild(wi);}
  ru.appendChild(sep());ru.appendChild(word('effort'));ru.appendChild(sep());ru.appendChild(el('span',{text:'output '}));ru.appendChild(word('output'));
  ru.appendChild(sep('→'));ru.appendChild(word('disposition'));
  var rt=routeFor(b);if(rt)ru.appendChild(el('a',{cls:'go',href:rt,text:'go',title:'open the place in the console where this gets done',onclick:function(e){e.preventDefault();e.stopPropagation();window.open(rt,'_blank');}}));
  body.appendChild(ru);
  var gz=el('div',{cls:'gauges'});[['importance','importance'],['urgency','urgency']].forEach(function(p){var ticks=el('span',{cls:'ticks'});
    for(var k=1;k<=5;k++)(function(k){ticks.appendChild(el('button',{cls:'tk'+((b[p[0]]||0)>=k?' on':''),title:p[0]+' '+k,onclick:function(e){e.stopPropagation();setField(b,p[0],k);rerenderBit(i);}}));})(k);
    gz.appendChild(el('span',{cls:'gauge','data-g':p[0]},[el('span',{text:p[1]}),ticks]));});
  body.appendChild(gz);
  var ns=el('input',{value:b.next_step||'',placeholder:'the first concrete move'});ns.addEventListener('input',function(){setField(b,'next_step',ns.value);});
  var nt=el('textarea',{rows:'1',placeholder:'a word from you'});nt.value=b.note||'';nt.addEventListener('input',function(){setField(b,'note',nt.value);});
  body.appendChild(el('div',{cls:'next'},[el('label',{text:'next step'}),ns,el('label',{text:'note'}),nt]));
  if(b.why)body.appendChild(el('div',{cls:'why',text:b.why}));
  var cb=careBlock(b,i);if(cb)body.appendChild(cb);
  // re-cutting the tape: split at a pause, merge with the next, ask for a new ruling
  var cuts=el('div',{cls:'cuts'});var cs=d.chunks||[];
  if(b.chunks&&b.chunks[1]>b.chunks[0]){cuts.appendChild(el('span',{text:'cut at'}));
    for(var q=b.chunks[0];q<b.chunks[1];q++)(function(q){var c=cs[q];if(!c)return;cuts.appendChild(el('a',{text:c.end!=null?mmss(c.end):('\u00b6'+(q-b.chunks[0]+1)),title:'split this bit after: '+(c.text||'').slice(0,80),onclick:function(e){e.stopPropagation();splitBit(i,q);}}));})(q);}
  if(i<(d.bits||[]).length-1)cuts.appendChild(el('a',{text:'merge with next',onclick:function(e){e.stopPropagation();mergeBit(i);}}));
  if(b.rerule)cuts.appendChild(el('span',{cls:'busy',text:'re-ruling, within two minutes'}));
  else cuts.appendChild(el('a',{cls:'rr',text:b.reruled_at?'rule again':'re-rule',title:'the reasoner rules on this bit alone',onclick:function(e){e.stopPropagation();b.rerule=true;b.edited=true;markDirty();rerenderBit(i);}}));
  if(b.rerule_error)cuts.appendChild(el('span',{text:'last re-rule failed: '+b.rerule_error}));
  body.appendChild(cuts);
  if(b.relates_to&&b.relates_to.length){var rel=el('div',{cls:'rel',text:'relates to'});b.relates_to.forEach(function(n){rel.appendChild(el('a',{href:'#bit-'+n,text:'#'+n,onclick:function(e){e.preventDefault();var t=$('#bit-'+n);if(t){t.scrollIntoView({block:'center',behavior:'smooth'});setCur(+t.getAttribute('data-i'),false);}}}));});body.appendChild(rel);}
  // echoes: the same thought said in other memos, computed by the pipeline
  if(b.echoes&&b.echoes.length){var ec=el('div',{cls:'rel',text:'also said in'});b.echoes.forEach(function(x){
    ec.appendChild(el('a',{href:'#memo='+x.memo,text:String(x.memo).slice(0,10)+' #'+x.n,title:(x.title||'')+' ('+Math.round((x.score||0)*100)+'%)',onclick:function(e){e.preventDefault();e.stopPropagation();gotoBit(x.memo,x.n);}}));});body.appendChild(ec);}
  // dispatch: the pipeline turned this signed bit into a job (or held it); the line links to the job as the console serves it
  var dl=dispatchLine(b);if(dl)body.appendChild(dl);
  var fl=fateLine(b,i);if(fl)body.appendChild(fl);
  var ab=askBlock(b,i);if(ab)body.appendChild(ab);
  var seal=el('div',{cls:'seal'},[
    el('button',{cls:'ok'+(so==='approved'?' on':''),html:ICON_OK,title:'approve this ruling; it is filed when you press done, file it (a)',onclick:function(e){e.stopPropagation();toggleSign(i,'approved');}}),
    el('button',{cls:'no'+(so==='rejected'?' on':''),html:ICON_NO,title:'reject: this bit is let go (r)',onclick:function(e){e.stopPropagation();toggleSign(i,'rejected');}}),
    so==='auto-pending'?el('span',{cls:'auto',title:'auto mode: approves itself at '+fmtDate(b.auto_at)+' unless you veto, approve or reject',text:'auto in '+(autoLeft(b)!=null?autoLeft(b):'?')+' min'}):null,
    so==='auto-pending'?el('button',{cls:'veto',text:'veto',title:'veto: this bit is let go and is never auto-approved (v)',onclick:function(e){e.stopPropagation();veto(i);}}):null,
    so==='approved'&&b.signoff_by==='auto'?el('span',{cls:'auto on',title:'approved by auto'+(b.signoff_at?' at '+fmtDate(b.signoff_at):'')+'; reject still rules',text:'auto'}):null,
    el('span',{cls:'conf',title:'how sure the reasoner is about this ruling',text:b.confidence!=null?Math.round(b.confidence*100)+'% sure':''}),b.edited?el('span',{cls:'ed',text:'edited'}):null]);
  card.appendChild(seal);
  return card;}

function drawStrip(cv,b,i){if(!cv||!b)return;var o=dpr(cv),g=o.g,w=o.w,h=o.h;g.clearRect(0,0,w,h);var col=DISPC[b.disposition]||DISPC.file;
  var wave=S.wave;if(!wave||!wave.peak||!wave.peak.length||b.start==null){g.fillStyle=col;g.globalAlpha=.4;g.fillRect(0,h/2,w,1);g.globalAlpha=1;return;}
  var dur=wave.duration||1,n=wave.peak.length,a=Math.floor(b.start/dur*n),z=Math.max(a+1,Math.ceil(b.end/dur*n)),m=z-a,bw=w/m;
  for(var k=0;k<m;k++){var v=Math.max(.04,wave.peak[a+k]||0)*h*.48;g.fillStyle=col;g.globalAlpha=S.playing===i?.95:.6;g.fillRect(k*bw,h/2-v,Math.max(.8,bw*.7),v*2);}g.globalAlpha=1;
  var cs=S.doc&&S.doc.chunks||[];if(b.chunks&&b.end>b.start){for(var q=b.chunks[0];q<b.chunks[1];q++){var c=cs[q];if(!c||c.end==null)continue;var x=(c.end-b.start)/(b.end-b.start)*w;g.fillStyle=C('--text');g.globalAlpha=.35;g.fillRect(x,0,1,h);g.globalAlpha=1;}}}

/* playback: one deck, the bit's clip when it exists, else the source seeked */
var deck=$('#deck');
function playBit(i,at){var d=S.doc,b=d.bits[i];if(!b)return;stopPlay(false);S.playing=i;
  var useClip=!!b.clip&&at==null;var src=DEMO?'':RAW(useClip?(MEMOS+'/'+d.id+'/'+b.clip):(d.source&&d.source.path||''));
  if(!src){S.playing=-1;return status(DEMO?'no audio in the demo':'no audio for this bit','err');}
  // preload is none on the element, so a new src never loads by itself: ask for it (2026-10-11: the clips were silent)
  if(deck.getAttribute('data-src')!==src){deck.preload='auto';deck.src=src;deck.setAttribute('data-src',src);deck.load();}
  S.stopAt=useClip?null:b.end;var start=useClip?0:(at!=null?at:b.start);
  var go=function(){try{deck.currentTime=start;}catch(e){}deck.play().catch(function(e){status('cannot play: '+e.message,'err');S.playing=-1;refreshPlay();});};
  if(deck.readyState>=1)go();else deck.addEventListener('loadedmetadata',go,{once:true});
  refreshPlay();}
function stopPlay(refresh){if(!deck.paused)deck.pause();S.playing=-1;S.stopAt=null;$('#tape .head')&&($('#tape .head').style.display='none');if(refresh!==false)refreshPlay();}
deck.addEventListener('timeupdate',function(){if(S.playing<0)return;var b=S.doc&&S.doc.bits[S.playing];if(!b)return;
  if(S.stopAt!=null&&deck.currentTime>=S.stopAt)return stopPlay();
  var head=$('#tape .head');if(head){var dur=(S.wave&&S.wave.duration)||(S.doc.source&&S.doc.source.duration)||1;var t=S.stopAt!=null?deck.currentTime:(b.start||0)+deck.currentTime;head.style.display='block';head.style.left=(t/dur*100)+'%';}});
deck.addEventListener('ended',function(){stopPlay();});
deck.addEventListener('error',function(){var e=deck.error;status('audio did not load'+(e?' (code '+e.code+')':'')+': '+(deck.getAttribute('data-src')||''),'err');S.playing=-1;refreshPlay();});
deck.addEventListener('stalled',function(){if(S.playing>=0)status('audio is stalling; the bridge may be slow','err');});
function refreshPlay(){drawTape();Array.prototype.forEach.call($$('.bit'),function(c){var i=+c.getAttribute('data-i');var pb=$('.play',c);if(pb){pb.classList.toggle('on',S.playing===i);pb.innerHTML=S.playing===i?ICON_STOP:ICON_PLAY;}
  var cv=$('.strip canvas',c);if(cv)drawStrip(cv,S.doc.bits[i],i);});}

function spanOf(b,a,z){var cs=S.doc.chunks||[];var part=cs.slice(a,z+1);b.chunks=[a,z];b.text=part.map(function(c){return c.text;}).join(' ').trim();
  b.start=part.length&&part[0].start!=null?part[0].start:null;b.end=part.length&&part[part.length-1].end!=null?part[part.length-1].end:null;b.clip=null;b.edited=true;b.signoff='pending';return b;}
function renumber(){(S.doc.bits||[]).forEach(function(b,k){b.n=k+1;});}
function splitBit(i,q){var bits=S.doc.bits,b=bits[i];var a=b.chunks[0],z=b.chunks[1];if(q<a||q>=z)return;
  var right=JSON.parse(JSON.stringify(b));spanOf(b,a,q);spanOf(right,q+1,z);right.title=(b.title||'')+' (ii)';right.relates_to=[];right.rerule=true;right.note='';
  bits.splice(i+1,0,right);renumber();markDirty();rerenderAll();setCur(i+1,false);status('cut. the second half asks for its own ruling; clips are re-cut within two minutes','ok');}
function mergeBit(i){var bits=S.doc.bits;if(i>=bits.length-1)return;var b=bits[i],nx=bits[i+1];spanOf(b,b.chunks[0],nx.chunks[1]);b.rerule=true;bits.splice(i+1,1);renumber();markDirty();rerenderAll();setCur(i,false);status('merged. one ruling for the joined bit within two minutes','ok');}
function toggleSign(i,v){var b=S.doc.bits[i];if(b.signoff===v){b.signoff='pending';delete b.signoff_by;}else{b.signoff=v;b.signoff_by=SIGNER;}markDirty();rerenderBit(i);}
function routeFor(b){var r=S.vocab&&S.vocab.routes;if(!r)return null;var o=r.output&&b.output&&r.output[b.output];if(o)return o;
  if(r.category_folder&&b.category)return r.category_folder.replace('{category}',encodeURIComponent(b.category));return null;}
// fate (TAPE-AUTO, 2026-11-15): what became of the bit, in one word and a link; a stale bit gets one press to revive it
function fateLine(b,i){var f=b.fate;if(!f||!f.word)return null;var line=el('div',{cls:'rel fate','data-w':f.word});
  line.appendChild(el('b',{text:f.word}));line.appendChild(el('span',{text:f.text||''}));
  if(f.link)line.appendChild(el('a',{href:f.link,text:'open',title:f.link,onclick:openUrl(f.link)}));
  if(f.word==='stale'){line.appendChild(el('button',{cls:'cl',text:'revive',title:'send it on as if it were new: an agent bit dispatches, a gated or taste bit goes to court',onclick:function(e){e.stopPropagation();
    if(DEMO)return status('demo: nothing written','ok');b.tape_auto={state:'revive',at:nowIso(),by:'tape'};b.fate={word:'queued',text:'revived: goes on with the next tape pass',link:f.link};S.dirty=true;
    save().then(function(){rerenderBit(i);status('revived; the next tape pass sends it on','ok');});}}));}
  return line;}
function dispatchLine(b){var d=b.dispatch;if(!d||!d.state)return null;var line=el('div',{cls:'rel disp','data-s':d.state});
  if(d.state==='sent'){line.appendChild(el('span',{text:'sent: '+(d.id||'')+(d.at?' · '+String(d.at).slice(0,10):'')}));
    if(d.url)line.appendChild(el('a',{href:d.url,text:'open',title:d.url,onclick:openUrl(d.url)}));
    if(d.board)line.appendChild(el('a',{href:d.board,text:'board',title:d.board,onclick:openUrl(d.board)}));}
  else if(d.state==='held')line.appendChild(el('span',{text:'held: '+(d.reason||''),title:'not opened by itself; change the when and save, and the watcher sends it'}));
  else if(d.state==='failed'&&!d.result)line.appendChild(el('span',{text:'dispatch failed: '+(d.error||'')+(d.attempts?' ('+d.attempts+'/3)':'')}));
  else{var r=d.result||{};var word={asks:'came back, asks you',answered:'came back, done',failed:'came back, failed rc '+r.rc,replied:'you replied; the follow-up job opens on the next dispatch pass'}[d.state]||d.state;
    line.appendChild(el('span',{text:word+': '+(d.id||'')+(r.finished_at?' · '+String(r.finished_at).slice(0,16).replace('T',' '):'')+(d.round>1?' · round '+d.round:'')}));
    if(r.answer){var au=consoleFile(r.answer);line.appendChild(el('a',{href:au,text:'answer',title:r.answer,onclick:openUrl(au)}));}
    if(d.url)line.appendChild(el('a',{href:d.url,text:'log',title:d.url,onclick:openUrl(d.url)}));
    (r.files||[]).forEach(function(f){var fu=consoleFile(f.charAt(0)==='/'||!WORLD?f:WORLD+'/'+f);line.appendChild(el('a',{href:fu,text:f.split('/').pop(),title:f,onclick:openUrl(fu)}));});}
  return line;}
function consoleFile(p){return location.origin+'/files?path='+encodeURIComponent(p);}
/* a link never takes the sentence's last mark: . , ; : ! ? quotes (curly too) * _ ~ and a bracket it did not open (FILES-ARCHIVE-1, same rule as lib/pathlinks.js tidyUrl) */
function tidyU(u){var s=String(u||''),P={')':'(',']':'[','}':'{','>':'<'};for(var i=0;i<40&&s;i++){var c=s.charAt(s.length-1);if(/[.,;:!?*_~'"\u2018\u2019\u201c\u201d\u00bb\u203a]/.test(c)){s=s.slice(0,-1);continue;}if(P[c]&&s.split(c).length>s.split(P[c]).length){s=s.slice(0,-1);continue;}break;}return s;}
/* a question from a job renders with its links clickable; **bold** and `code` are kept as plain text */
function renderQ(q){var box=el('div',{cls:'q'});var t=String(q||'').replace(/\*\*/g,'').replace(/`/g,'');var re=/https?:\/\/[^\s)\]>"'`]+/g,last=0,m;
  while((m=re.exec(t))){box.appendChild(document.createTextNode(t.slice(last,m.index)));var u=tidyU(m[0]);box.appendChild(el('a',{href:u,text:u,target:'_blank',rel:'noopener'}));last=m.index+u.length;}
  box.appendChild(document.createTextNode(t.slice(last)));return box;}
function askBlock(b,i){var d=b.dispatch;if(!d||!d.result||['asks','answered','failed'].indexOf(d.state)<0)return null;var r=d.result;
  var box=el('div',{cls:'ask'});var k=(d.replies||[]).length;
  if(d.state==='asks'){box.appendChild(el('div',{cls:'k',text:'the job asks you'+(k?' (round '+((d.round||1))+')':'')}));box.appendChild(renderQ(r.question));}
  else box.appendChild(el('div',{cls:'q dim',text:d.state==='answered'?'no question; reply to send the job further':'the job failed (rc '+r.rc+'); reply to send it again with your words'}));
  var inp=el('input',{placeholder:d.state==='asks'?'your answer, one line; enter sends':'what should it do next'});var btn=el('button',{text:'send'});
  var go=function(){var t=inp.value.trim();if(!t)return inp.focus();sendReply(b,i,t,box);};
  inp.addEventListener('keydown',function(e){if(e.key==='Enter'){e.preventDefault();go();}});inp.addEventListener('click',function(e){e.stopPropagation();});
  btn.addEventListener('click',function(e){e.stopPropagation();go();});
  box.appendChild(el('div',{cls:'reply'},[inp,btn]));return box;}
function sendReply(b,i,text,box){var d=S.doc;if(!d||DEMO)return status('demo: nothing written','ok');if(S.dirty)return status('save your edits first, then reply','err');
  var k=((b.dispatch||{}).replies||[]).length+1,n=b.n<10?'0'+b.n:String(b.n);var rp=MEMOS+'/'+d.id+'/dispatch/bit-'+n+'.reply-'+k+'.md';
  box.classList.add('busy');
  writeText(rp,text+'\n',null).then(function(res){if(!res.ok)throw new Error(res.error||res._status||'write refused');
    var x=b.dispatch;x.replies=(x.replies||[]).concat([{k:k,path:rp,at:nowIso(),to:x.id,by:'tape'}]);x.state='replied';x.reply=rp;S.dirty=true;return save();}).then(function(){
    box.classList.remove('busy');rerenderBit(i);status('reply kept; the follow-up job opens on the next dispatch pass (within a minute while the door is open)','ok');})
  .catch(function(e){box.classList.remove('busy');status('reply failed: '+e.message+'; press send again','err');});}
function gotoBit(memo,n){setView('tape');return select(memo).then(function(){if(S.id!==memo)return;var t=$('#bit-'+n);if(t){t.scrollIntoView({block:'center',behavior:'smooth'});setCur(+t.getAttribute('data-i'),false);}});}
function setCur(i,scroll){if(!S.doc||!S.doc.bits||!S.doc.bits.length)return;var n=S.doc.bits.length;i=Math.max(0,Math.min(n-1,i));
  var cards=$('#bits').children;if(S.cur>=0&&cards[S.cur])cards[S.cur].classList.remove('cur');S.cur=i;if(cards[i]){cards[i].classList.add('cur');if(scroll)cards[i].scrollIntoView({block:'center',behavior:'smooth'});}drawTape();}

/* popover */
var pop=$('#pop');
function openPop(anchor,field,current,onPick){if(S.popFor===anchor){closePop();return;}closePop();S.popFor=anchor;anchor.classList.add('open');
  var opts=(S.vocab&&S.vocab[field])||[];var hints=(S.vocab&&S.vocab.category_hint)||{};pop.innerHTML='';
  opts.forEach(function(o){var bt=el('button',{cls:o===current?'cur':'',text:o,onclick:function(e){e.stopPropagation();closePop();onPick(o);}});
    if(field==='category'&&hints[o])bt.appendChild(el('small',{text:hints[o]}));pop.appendChild(bt);});
  var r=anchor.getBoundingClientRect(),o=root.getBoundingClientRect();pop.style.display='block';var left=r.left-o.left,topY=r.bottom-o.top+6;
  if(r.left+pop.offsetWidth>window.innerWidth-8)left=Math.max(8,window.innerWidth-pop.offsetWidth-8)-o.left;
  pop.style.left=left+'px';pop.style.top=topY+'px';var cb=pop.querySelector('button.cur')||pop.querySelector('button');if(cb)cb.focus({preventScroll:true});}
function closePop(){pop.style.display='none';pop.innerHTML='';if(S.popFor)S.popFor.classList.remove('open');S.popFor=null;}
on(document,'mousedown',function(e){if(pop.style.display==='block'&&!pop.contains(e.target)&&e.target!==S.popFor)closePop();});

/* save / done */
function save(){var d=S.doc;if(!d||S.saving)return Promise.resolve();clearTimeout(S.timer);S.saving=true;updateBar();var id=d.id;
  return writeText(bitsPath(id),JSON.stringify(d,null,2)+'\n',S.mtime).then(function(res){S.saving=false;
    if(res._status===409||res.conflict){status('bits.json changed on disk meanwhile; reloaded, your last edits were not saved','err');S.dirty=false;return select(id,true);}
    if(!res.ok){status('save failed: '+(res.error||res._status),'err');updateBar();return;}
    S.dirty=false;if(res.mtime!=null){S.mtime=res.mtime;updateBar();return loadIndex();}
    return listing(bitsPath(id)).then(function(l){S.mtime=l.mtime;}).catch(function(){}).then(function(){updateBar();return loadIndex();});})
  .catch(function(e){S.saving=false;status('save error: '+e.message,'err');updateBar();});}
function doneFile(){var d=S.doc;if(!d)return;if(pending(d))return status(pending(d)+' bits still pending','err');
  if(!confirm('Review done? The approved bits are filed and the act bits queued within two minutes.'))return;
  d.review=d.review||{};d.review.done=true;d.review.done_at=nowIso();S.dirty=true;save().then(function(){status('done. filing within two minutes','ok');});}

/* ---------- views: the tape (one memo) or the board (every bit) ---------- */
function setView(v,hash){if(v!=='board')v='tape';var was=S.view;S.view=v;closePop();
  Array.prototype.forEach.call($$('#shelf .views button'),function(bt){bt.classList.toggle('on',bt.getAttribute('data-v')===v);});
  $('#memo').style.display=v==='tape'?'':'none';$('#board').style.display=v==='board'?'':'none';
  if(v==='board'){if(hash!==false&&location.hash!=='#board')history.replaceState(null,'','#board');if(was!=='board'||!S.board)loadBoard();startBoardPoll();}
  else{stopBoardPoll();if(hash!==false&&location.hash==='#board')history.replaceState(null,'',S.id?'#memo='+S.id:location.pathname+location.search);}}
Array.prototype.forEach.call($$('#shelf .views button'),function(bt){bt.addEventListener('click',function(){setView(bt.getAttribute('data-v'));});});
function startBoardPoll(){stopBoardPoll();if(DEMO)return;S.boardTimer=every(function(){if(S.view!=='board'||document.hidden)return;loadBoard();},20000);}
function stopBoardPoll(){if(S.boardTimer)clearInterval(S.boardTimer);S.boardTimer=null;}

/* the board: data */
var BOARD_PATH=MEMOS+'/board.json',LIVE={open:1,pending:1,signed:1};
var BF_WHO=['all','me','agent','me+agent','other'],BF_STATE=['live','open','pending','signed','done','all'];
function loadBF(){var j={};try{j=JSON.parse(localStorage.getItem('memos.board')||'{}')||{};}catch(e){}
  S.bf={who:BF_WHO.indexOf(j.who)>=0?j.who:'all',state:BF_STATE.indexOf(j.state)>=0?j.state:'live',q:typeof j.q==='string'?j.q:'',care:j.care==='needs a look'?'needs a look':'all'};}
function saveBF(){try{localStorage.setItem('memos.board',JSON.stringify(S.bf));}catch(e){}}
function demoBoard(){var sts=['signed','open','pending','rejected','open'];return {generated:nowIso(),bits:DEMO_BITS.map(function(b,i){var x=JSON.parse(JSON.stringify(b));
  x.memo=DEMO_DOC.id;x.memo_title=DEMO_DOC.title;x.memo_created=DEMO_DOC.created;x.memo_stage='decided';x.filed=false;x.status=sts[i];return x;})};}
function loadBoard(){if(DEMO){S.board=demoBoard();renderBoard();return Promise.resolve();}
  return getJSON(RAW(BOARD_PATH)).then(function(b){S.boardErr=false;S.board=b&&b.bits?b:{bits:[]};renderBoard();})
  .catch(function(e){S.boardErr=true;if(!S.board){S.board={bits:[]};}renderBoard();if(S.view==='board')status('board.json: '+e.message,'err');});}
function isYours(b){return b.who==='me'||b.who==='me+agent';}
function isAgents(b){return b.who==='agent'||b.who==='me+agent';}
function stOf(b){var st=b.status||'pending';return st==='auto-pending'?'pending':st;}
function bfPass(b){var f=S.bf,st=stOf(b);
  if(f.who!=='all'&&b.who!==f.who)return false;
  if(f.care==='needs a look')return careOpen(b);
  if(f.state==='live'){if(!LIVE[st])return false;}else if(f.state!=='all'&&st!==f.state)return false;
  if(f.q){var q=f.q.toLowerCase();if(((b.title||'')+' '+(b.text||'')+' '+(b.category||'')).toLowerCase().indexOf(q)<0)return false;}
  return true;}
function openUrl(u){return function(e){e.preventDefault();e.stopPropagation();window.open(u,'_blank');};}

/* the board: render */
function renderBoard(){var box=$('#board');if(!S.bf)loadBF();box.innerHTML='';
  box.appendChild(el('div',{cls:'hdr'},[el('div',{cls:'kicker mono',text:'board · every thought on the tape'+(S.board&&S.board.generated?' · as of '+fmtDate(S.board.generated):'')}),el('h2',{text:'What is open.'})]));
  box.appendChild(el('div',{cls:'btot',id:'btot'}));
  var fl=el('div',{cls:'bfilt'});
  var chips=function(label,key,opts){var g=el('span',{cls:'grp'},[el('span',{text:label})]);opts.forEach(function(o){
    g.appendChild(el('button',{cls:'w'+(S.bf[key]===o?' open':''),text:o,onclick:function(){S.bf[key]=o;saveBF();Array.prototype.forEach.call(g.querySelectorAll('.w'),function(c){c.classList.toggle('open',c.textContent===o);});renderGroups();}}));});return g;};
  fl.appendChild(chips('who ','who',BF_WHO));fl.appendChild(chips('state ','state',BF_STATE));fl.appendChild(chips('care ','care',['all','needs a look']));
  var qi=el('input',{value:S.bf.q,placeholder:'title, text or category'});var qt=null;qi.addEventListener('input',function(){S.bf.q=qi.value.trim();saveBF();clearTimeout(qt);qt=setTimeout(renderGroups,180);});fl.appendChild(qi);
  box.appendChild(fl);box.appendChild(el('div',{id:'bgroups'}));renderGroups();}
function renderTotals(){var t=$('#btot');if(!t)return;var bs=S.board&&S.board.bits||[];var n=bs.length,a=0,b=0,c=0,d=0,e=0;
  var ny=0,nc=0;bs.forEach(function(x){var st=stOf(x);if(st==='pending')a++;else if(st==='open'){b++;if(isYours(x))c++;if(isAgents(x))d++;}else if(st==='done')e++;if(x.dispatch&&x.dispatch.state==='asks')ny++;if(careOpen(x))nc++;});
  t.innerHTML='<b>'+n+'</b> thought'+(n===1?'':'s')+' &middot; <b>'+a+'</b> pending your seal &middot; <b>'+b+'</b> to act (<b>'+c+'</b> yours, <b>'+d+'</b> the agent’s) &middot; <b>'+e+'</b> done'
    +(ny?' &middot; <span class="needs"><b>'+ny+'</b> job'+(ny===1?'':'s')+' need'+(ny===1?'s':'')+' you</span>':'')
    +(nc?' &middot; <span class="needs"><b>'+nc+'</b> need'+(nc===1?'s':'')+' a look</span>':'');}
function groupCount(cat){var l=0,d=0;(S.board&&S.board.bits||[]).forEach(function(x){if(x.category!==cat)return;var st=stOf(x);if(LIVE[st])l++;else if(st==='done')d++;});return l+' live · '+d+' done';}
function renderGroups(){var holder=$('#bgroups');if(!holder)return;holder.innerHTML='';renderTotals();var bs=S.board&&S.board.bits||[];
  if(!bs.length){holder.appendChild(el('div',{cls:'empty',text:S.boardErr?'no board.json yet; the pipeline writes it within two minutes':'nothing on the board yet'}));return;}
  var shown=bs.filter(bfPass);if(!shown.length){holder.appendChild(el('div',{cls:'empty',text:'nothing matches; widen the filter'}));return;}
  var by={},live={};bs.forEach(function(x){var c=x.category||'other';if(LIVE[stOf(x)])live[c]=(live[c]||0)+1;});
  shown.forEach(function(x){var c=x.category||'other';(by[c]=by[c]||[]).push(x);});
  var cats=Object.keys(by).sort(function(p,q){return (live[q]||0)-(live[p]||0)||by[q].length-by[p].length||p.localeCompare(q);});
  var r=S.vocab&&S.vocab.routes||{};
  cats.forEach(function(cat){var gh=el('div',{cls:'gh'},[el('h3',{text:cat}),el('span',{cls:'cnt','data-cat':cat,text:groupCount(cat)})]);
    var gl=el('span',{cls:'gl'});
    if(r.category_folder){var fu=r.category_folder.replace('{category}',encodeURIComponent(cat));gl.appendChild(el('a',{cls:'lnk',href:fu,text:'folder',title:'open the system folder in the console',onclick:openUrl(fu)}));}
    if(r.category_digest){var du=r.category_digest.replace('{category}',encodeURIComponent(cat));gl.appendChild(el('a',{cls:'lnk',href:du,text:'digest',title:'open the category digest in the console',onclick:openUrl(du)}));}
    gh.appendChild(gl);var g=el('section',{cls:'bgrp'},[gh]);
    by[cat].sort(function(p,q){return (q.urgency||0)-(p.urgency||0)||(q.importance||0)-(p.importance||0);}).forEach(function(x){g.appendChild(renderRow(x));});
    holder.appendChild(g);});}
function renderRow(b){var st=b.status||'pending';var row=el('div',{cls:'brow'});
  var dot=el('span',{cls:'dot'});dot.style.background=DISPC[b.disposition]||DISPC.file;row.appendChild(dot);
  var ti=el('button',{cls:'ti',text:b.title||'(untitled)',title:(b.text||'').slice(0,200)+(b.memo_title?'\n\nfrom: '+b.memo_title:''),onclick:function(){gotoBit(b.memo,b.n);}});
  var when=b.act_when==='date'&&b.act_date?b.act_date:b.act_when,who=b.who==='other'&&b.who_name?b.who_name:b.who;
  var ru=el('div',{cls:'ru',text:[when,who,b.effort,b.output].filter(Boolean).join(' · ')});var dd=b.dispatch;
  if(dd&&dd.state==='sent')ru.appendChild(el('span',{cls:'dsp'},[el('span',{text:'· '}),el('a',{href:dd.url||'#',text:'sent '+(dd.id||''),title:dd.url||'',onclick:openUrl(dd.url||'#')})]));
  else if(dd&&dd.state==='asks')ru.appendChild(el('span',{cls:'dsp','data-s':'asks'},[el('span',{text:'· '}),el('a',{href:'#memo='+b.memo,text:'asks you',title:(dd.result&&dd.result.question||'').slice(0,300),onclick:function(e){e.preventDefault();e.stopPropagation();gotoBit(b.memo,b.n);}})]));
  else if(dd&&dd.state)ru.appendChild(el('span',{cls:'dsp',text:'· '+dd.state,title:dd.reason||dd.error||(dd.result&&dd.result.question)||''}));
  if(careOpen(b))ru.appendChild(el('span',{cls:'cm',text:'look',title:b.care.map(function(c){return (CARE_LABEL[c.flag]||c.flag)+': '+c.why;}).join('\n')}));
  if(b.signoff==='auto-pending')ru.appendChild(el('span',{cls:'auto',text:'auto in '+(autoLeft(b)!=null?autoLeft(b):'?')+' min',title:'approves itself unless vetoed on the tape'}));
  else if(b.signoff==='approved'&&b.signoff_by==='auto')ru.appendChild(el('span',{cls:'auto',text:'auto',title:'approved by auto'}));
  row.appendChild(el('div',{},[ti,ru]));
  row.appendChild(el('span',{cls:'dt',text:String(b.memo||'').slice(0,10),title:b.memo_title||b.memo}));
  row.appendChild(el('span',{cls:'st','data-s':st,text:st}));
  var ops=el('span',{cls:'ops'});
  if(st==='open'){ops.appendChild(el('button',{text:'done',title:'the work is done',onclick:function(){markBit(b,'done',row);}}));ops.appendChild(el('button',{text:'drop',title:'let it go without doing it',onclick:function(){markBit(b,'dropped',row);}}));}
  else if(st==='done'||st==='dropped')ops.appendChild(el('button',{text:'reopen',title:'back to open',onclick:function(){markBit(b,'open',row);}}));
  row.appendChild(ops);return row;}
function refreshCounts(){renderTotals();Array.prototype.forEach.call($$('#bgroups .cnt'),function(c){c.textContent=groupCount(c.getAttribute('data-cat'));});}

/* the board: marking done / dropped / open writes status into that memo's bits.json; the watcher follows */
function markBit(b,to,row){var id=b.memo;if(!id||!b.n)return status('this row has no memo behind it','err');
  if(S.id===id&&S.dirty)return status('that memo has unsaved edits on the tape; save them first','err');
  if(DEMO){b.status=to;row.replaceWith(renderRow(b));refreshCounts();return status('demo: nothing written','ok');}
  row.classList.add('busy');var mt=null;
  listing(bitsPath(id)).then(function(l){mt=l&&l.mtime!=null?l.mtime:null;return getJSON(RAW(bitsPath(id)));}).then(function(doc){
    var x=(doc.bits||[])[b.n-1];if(!x||(x.n!=null&&x.n!==b.n))throw new Error('bit #'+b.n+' is not where the board expects it in '+id+'; the tape may have been re-cut');
    x.status=to;doc.queue_dirty=true;return writeText(bitsPath(id),JSON.stringify(doc,null,2)+'\n',mt);}).then(function(res){row.classList.remove('busy');
    if(res._status===409||res.conflict)return status('bits.json of '+id+' changed on disk meanwhile; nothing written. try again','err');
    if(!res.ok)return status('mark failed: '+(res.error||res._status),'err');
    b.status=to;row.replaceWith(renderRow(b));refreshCounts();if(S.id===id&&!S.dirty)select(id,true);
    status(to==='open'?'reopened; the queue and the category files follow within two minutes':'marked '+to+'; the queue and the category files follow within two minutes','ok');})
  .catch(function(e){row.classList.remove('busy');status('mark failed: '+e.message,'err');});}

/* intake */
var plate=$('#plate'),mainEl=$('#main'),dragN=0;
$('#choose').addEventListener('click',function(){$('#file').click();});
$('#writeToggle').addEventListener('click',function(){plate.classList.toggle('words-open');if(plate.classList.contains('words-open'))$('#txt').focus();});
$('#file').addEventListener('change',function(){if(this.files.length)uploadFiles(Array.prototype.slice.call(this.files));this.value='';});
on(document,'dragenter',function(e){e.preventDefault();dragN++;plate.classList.add('over');});
on(document,'dragover',function(e){e.preventDefault();});
on(document,'dragleave',function(){dragN=Math.max(0,dragN-1);if(!dragN)plate.classList.remove('over');});
on(document,'drop',function(e){e.preventDefault();dragN=0;plate.classList.remove('over');
  var fs=Array.prototype.slice.call(e.dataTransfer&&e.dataTransfer.files||[]);
  fs=fs.filter(function(f){return /^(audio|video)\//.test(f.type)||/\.(m4a|mp3|wav|ogg|oga|opus|webm|aac|flac|mp4|mov|mkv|caf|aiff?)$/i.test(f.name);});
  if(!fs.length)return status('nothing audio or video in that drop','err');uploadFiles(fs);});
var UPLOAD_MAX=50*1048576;   // the bridge's limit per request
function uploadFiles(files){var rows=files.map(function(f){var bar=el('i');var r=el('div',{cls:'prog'},[el('span',{text:f.name+' \u00b7 '+(Math.round(f.size/1048576*10)/10)+' MB \u00b7 '}),el('span',{cls:'st',text:'waiting'}),el('div',{cls:'bar'},[bar])]);r._bar=bar;r._file=f;$('#progs').appendChild(r);return r;});
  if(DEMO){rows.forEach(function(r){r._bar.style.width='100%';$('.st',r).textContent='demo: nothing sent';});return;}
  var k=0,okN=0;
  function next(){if(k>=rows.length){if(okN)status(okN+' received; transcribing within two minutes','ok');[20,70,130,190].forEach(function(s){setTimeout(loadIndex,s*1000);});return;}
    var r=rows[k++],f=r._file;
    if(f.size>UPLOAD_MAX){$('.st',r).textContent='too big for the page (limit 50 MB per file); ask the brain to take it from the box';return next();}
    $('.st',r).textContent='uploading';
    var fd=new FormData();fd.append('file',f,f.name);
    var xhr=new XMLHttpRequest();xhr.open('POST','/cc/upload');xhr.withCredentials=true;
    xhr.upload.onprogress=function(e){if(!e.lengthComputable)return;var pct=Math.round(e.loaded/e.total*100);r._bar.style.width=pct+'%';$('.st',r).textContent='uploading '+pct+'%';};
    xhr.onerror=function(){$('.st',r).textContent='upload failed (network); drop it again';next();};
    xhr.onload=function(){var j=null;try{j=JSON.parse(xhr.responseText);}catch(e){}
      if(xhr.status<200||xhr.status>=300||!j||!j.ok){$('.st',r).textContent='failed: '+((j&&j.error)||('http '+xhr.status));return next();}
      r._bar.style.width='100%';var sf=(j.files||[])[0];if(!sf){$('.st',r).textContent='saved, but the bridge named no file';return next();}
      writeText(INBOX+'/'+sf.name+'.take.txt',sf.path).then(function(res){$('.st',r).textContent=res.ok?'received \u00b7 on the tape within two minutes':'saved but the marker failed: '+(res.error||res._status);if(res.ok)okN++;}).catch(function(e){$('.st',r).textContent='marker failed: '+e.message;}).then(next);};
    xhr.send(fd);}
  next();}
$('#take').addEventListener('click',function(){var t=$('#txt').value.trim();if(!t)return;var p=INBOX+'/text-'+Math.floor(Date.now()/1000)+'.txt';$('#txtres').textContent='writing';
  writeText(p,t+'\n').then(function(res){if(res.ok){$('#txt').value='';$('#txtres').textContent='received · a memo within two minutes';[20,70,130].forEach(function(s){setTimeout(loadIndex,s*1000);});}else $('#txtres').textContent='failed: '+(res.error||res._status);})
  .catch(function(e){$('#txtres').textContent='failed: '+e.message;});});

/* talk-through (TALK-1, 2026-11-13). Tap: the mic opens, MediaRecorder hands over a slice every 10 s and each
   slice is uploaded at once through the console's own /cc/upload (it lands as in/<date>/talk-<id>-NNNN.<ext>.part),
   then inbox/talk-<id>.rec.json is rewritten with the parts so far. Tap again: the last slice goes and the manifest
   is marked done; the watcher stitches the parts into one take and cuts it at the pauses like a dropped file.
   An hour is 360 slices of a few hundred KB, none held only in the browser for more than one upload. If the page
   dies, the parts already on the box are taken after 30 minutes of quiet. */
var R={rec:null,stream:null,ctx:null,an:null,buf:null,raf:0,tick:0,t0:0,id:'',ext:'webm',mime:'',started:'',parts:[],q:[],n:0,up:false,stopping:false,fails:0,lock:null,hist:[]};
var talkEl=$('#talk'),recNote=$('#recNote'),recClock=$('#recClock'),recLvl=$('#recLvl');
function recSay(t){recNote.textContent=t;}
function recPick(){var c=['audio/webm;codecs=opus','audio/webm','audio/mp4','audio/ogg;codecs=opus'];for(var i=0;i<c.length;i++){try{if(window.MediaRecorder&&MediaRecorder.isTypeSupported(c[i]))return c[i];}catch(e){}}return '';}
function recManifest(done){var m={id:R.id,ext:R.ext,mime:R.mime,started:R.started,parts:R.parts.slice(),done:!!done,at:new Date().toISOString(),seconds:Math.round((Date.now()-R.t0)/1000)};
  return writeText(INBOX+'/talk-'+R.id+'.rec.json',JSON.stringify(m)+'\n');}
function recPump(){if(R.up)return;if(!R.q.length){if(R.stopping&&!R.rec)recFinish();return;}
  R.up=true;var job=R.q[0];var nm='talk-'+R.id+'-'+('000'+job.k).slice(-4)+'.'+R.ext+'.part';
  if(DEMO){R.q.shift();R.parts.push('/demo/'+nm);R.up=false;recShow();return recPump();}
  var fd=new FormData();fd.append('file',job.blob,nm);
  fetch('/cc/upload',{method:'POST',credentials:'same-origin',body:fd}).then(function(r){return r.json().catch(function(){return {ok:false,error:'http '+r.status};});})
  .then(function(j){var f=j&&j.ok&&(j.files||[])[0];if(!f)throw new Error((j&&j.error)||'no file named');R.q.shift();R.parts.push(f.path);R.fails=0;
    return recManifest(false).then(function(res){if(!res.ok)throw new Error('manifest: '+(res.error||res._status));});})
  .then(function(){R.up=false;recShow();recPump();})
  .catch(function(e){R.up=false;R.fails++;recShow('the box did not take a slice ('+e.message+'); retrying, the sound is kept here');setTimeout(recPump,Math.min(30000,2000*R.fails));});}
function recShow(err){if(err)return recSay(err);var w=R.q.length;
  if(R.stopping)recSay(w?'sending the last '+(w>1?w+' slices':'slice')+'\u2026':'finishing\u2026');
  else recSay(R.parts.length+' slice'+(R.parts.length===1?'':'s')+' safe on the box'+(w>1?' \u00b7 '+w+' waiting':'')+' \u00b7 tap to stop');}
function recFinish(){recManifest(true).then(function(res){talkEl.className='';
  if(!res.ok){recSay('the take is on the box but the last note failed ('+(res.error||res._status)+'); it is taken in 30 minutes anyway');return;}
  var secs=Math.round((Date.now()-R.t0)/1000);recSay(mmss(secs)+' sent \u00b7 cut and on the tape within a few minutes \u00b7 tap to talk again');status('take received; the watcher cuts it within two minutes','ok');
  [60,150,300].forEach(function(s){setTimeout(loadIndex,s*1000);});}).catch(function(e){talkEl.className='';recSay('last note failed: '+e.message+'; taken in 30 minutes anyway');});
  R.stopping=false;}
function recDraw(){var c=recLvl,w=c.clientWidth||300,h=28,dpr=window.devicePixelRatio||1;if(c.width!==w*dpr){c.width=w*dpr;c.height=h*dpr;}
  var g=c.getContext('2d');g.setTransform(dpr,0,0,dpr,0,0);g.clearRect(0,0,w,h);var lv=0;
  if(R.an){R.an.getFloatTimeDomainData(R.buf);var s=0;for(var i=0;i<R.buf.length;i++)s+=R.buf[i]*R.buf[i];lv=Math.min(1,Math.sqrt(s/R.buf.length)*4);}
  R.hist.push(lv);var n=Math.floor(w/3);if(R.hist.length>n)R.hist.splice(0,R.hist.length-n);
  g.fillStyle=C('--delete')||'#c87878';for(var k=0;k<R.hist.length;k++){var v=Math.max(1,R.hist[k]*h);g.globalAlpha=.35+.65*(k/R.hist.length);g.fillRect(w-(R.hist.length-k)*3,(h-v)/2,2,v);}
  g.globalAlpha=1;talkEl.style.setProperty('--lvl',lv.toFixed(2));recClock.textContent=mmss((Date.now()-R.t0)/1000);
  if(R.rec)R.raf=requestAnimationFrame(recDraw);}
function recStart(){if(!(navigator.mediaDevices&&navigator.mediaDevices.getUserMedia&&window.MediaRecorder))return recSay('this browser cannot record');
  recSay('opening the mic\u2026');
  /* the level meter's AudioContext is made inside the tap: Safari only lets a context run if it was born in a gesture */
  var AC=window.AudioContext||window.webkitAudioContext,ctx=null;try{ctx=AC?new AC():null;}catch(e){ctx=null;}
  navigator.mediaDevices.getUserMedia({audio:true}).then(function(stream){
    R.mime=recPick();R.ext=/mp4/.test(R.mime)?'m4a':/ogg/.test(R.mime)?'ogg':'webm';
    try{R.rec=R.mime?new MediaRecorder(stream,{mimeType:R.mime}):new MediaRecorder(stream);}catch(e){stream.getTracks().forEach(function(t){t.stop();});try{ctx&&ctx.close();}catch(x){}return recSay('could not start recording');}
    if(!R.mime){var mt=R.rec.mimeType||'';R.ext=/mp4/.test(mt)?'m4a':/ogg/.test(mt)?'ogg':'webm';}
    var d=new Date(),p=function(x){return (x<10?'0':'')+x;};
    R.id=d.getUTCFullYear()+p(d.getUTCMonth()+1)+p(d.getUTCDate())+'-'+p(d.getUTCHours())+p(d.getUTCMinutes())+p(d.getUTCSeconds())+'-'+Math.random().toString(36).slice(2,6);
    R.started=d.toISOString().slice(0,19)+'Z';R.stream=stream;R.parts=[];R.q=[];R.n=0;R.hist=[];R.fails=0;R.stopping=false;R.t0=Date.now();
    R.rec.ondataavailable=function(e){if(e.data&&e.data.size){R.q.push({k:++R.n,blob:e.data});recPump();}};
    R.rec.onstop=function(){R.stream.getTracks().forEach(function(t){t.stop();});R.rec=null;cancelAnimationFrame(R.raf);
      try{R.ctx&&R.ctx.close();}catch(e){}R.ctx=R.an=null;try{R.lock&&R.lock.release();}catch(e){}R.lock=null;recShow();recPump();};
    try{R.ctx=ctx;var src=R.ctx.createMediaStreamSource(stream);R.an=R.ctx.createAnalyser();R.an.fftSize=1024;
      R.buf=new Float32Array(R.an.fftSize);src.connect(R.an);if(R.ctx.state==='suspended')R.ctx.resume();}catch(e){R.an=null;}
    try{navigator.wakeLock&&navigator.wakeLock.request('screen').then(function(l){R.lock=l;}).catch(function(){});}catch(e){}
    R.rec.start(10000);talkEl.className='on';recSay('recording \u00b7 tap to stop');recDraw();})
  .catch(function(e){try{ctx&&ctx.close();}catch(x){}recSay(e&&e.name==='NotAllowedError'?('the mic was refused; allow it for this site and tap again'):'no mic: '+((e&&e.message)||e));});}
function recStop(){if(!R.rec)return;R.stopping=true;talkEl.className='busy';try{R.rec.stop();}catch(e){}recShow();}
$('#recBtn').addEventListener('click',function(){if(R.rec)recStop();else if(!R.stopping&&!R.up&&!R.q.length)recStart();});
on(window,'beforeunload',function(e){if(R.rec||R.q.length){e.preventDefault();e.returnValue='';}});
if(opts.expose)window.__talk=R;


/* keyboard */
on(document,'keydown',function(e){if(e.key==='Escape'){closePop();stopPlay();return;}
  var t=e.target;if(t&&(t.tagName==='INPUT'||t.tagName==='TEXTAREA'||t.isContentEditable))return;if(e.ctrlKey||e.metaKey||e.altKey)return;
  if(S.view==='board')return; /* the tape's keys must not seal a hidden memo */
  if(pop.style.display==='block'){if(e.key==='ArrowDown'||e.key==='ArrowUp'){e.preventDefault();var bs=Array.prototype.slice.call(pop.querySelectorAll('button')),k=bs.indexOf(document.activeElement);var nk=e.key==='ArrowDown'?Math.min(bs.length-1,k+1):Math.max(0,k-1);if(bs[nk])bs[nk].focus();}return;}
  if(!S.doc||!S.doc.bits||!S.doc.bits.length){if(e.key==='s')save();return;}
  if(e.key==='j'){setCur(S.cur+1,true);}else if(e.key==='k'){setCur(S.cur-1,true);}
  else if(e.key===' '&&S.cur>=0){e.preventDefault();if(S.playing===S.cur)stopPlay();else playBit(S.cur);}
  else if(e.key==='a'&&S.cur>=0){toggleSign(S.cur,'approved');}else if(e.key==='r'&&S.cur>=0){toggleSign(S.cur,'rejected');}else if(e.key==='v'&&S.cur>=0){veto(S.cur);}
  else if(e.key==='s'){if(S.dirty)save();}});
on(window,'resize',function(){drawTape();rerenderStrips();renderList();});

/* polling */
if(!DEMO){every(function(){loadIndex();},15000);
  every(function(){if(!S.id||S.dirty||S.saving)return;var id=S.id;
    listing(bitsPath(id)).then(function(l){if(S.id!==id||S.dirty)return;if(l&&l.mtime!=null&&l.mtime!==S.mtime){var y=window.scrollY;select(id,true).then(function(){window.scrollTo(0,y);});}})
    .catch(function(){if(!S.doc)select(id,true);});},10000);}
on(window,'beforeunload',function(e){if(S.dirty){e.preventDefault();e.returnValue='';}});

var dirEl=$('#tpDir');if(dirEl)dirEl.textContent=DEMO?'the tape folder':MEMOS;
/* boot: #memo=<id> opens the tape on that memo, #board opens the board over the newest memo */
on(window,'hashchange',function(){var h=location.hash;if(h==='#board')return setView('board',false);
  if(/^#memo=/.test(h)){setView('tape',false);var id=decodeURIComponent(h.slice(6));if(id!==S.id&&indexEntry(id))select(id);}});
loadVocab().then(loadIndex).then(function(){var h=location.hash.replace(/^#memo=/,'');var ms=S.index&&S.index.memos||[];
  if(h&&h!=='#board'&&indexEntry(h))return select(h);if(ms.length)return select(ms.slice().sort(function(a,b){return String(b.created||'').localeCompare(String(a.created||''));})[0].id);})
  .then(function(){if(location.hash==='#board')setView('board',false);})
  .catch(function(e){status('boot error: '+e.message,'err');});

  } catch (e) {
    root.textContent = 'the tape did not start: ' + (e && e.message)
  }
  return function unmount() {
    offs.forEach(function (f) { try { f() } catch (e) {} })
    timers.forEach(function (id) { clearInterval(id) })
    try { if (R && R.rec) R.rec.stop() } catch (e) {}
    try { if (S && S.timer) clearTimeout(S.timer) } catch (e) {}
    root.innerHTML = ''
  }
}
