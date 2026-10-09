# CC: talk to your brain, with a reasoner on your own server

Created: 2026-09-15. Applies to brainfoundry-nous 0.12.0 and later; hands and writes from 0.13.0.

CC is the first tab in the brain console. You type, the brain answers in its own voice, and the answer is grounded in what the brain remembers about you and in its own files. Behind it runs a reasoner on your server: the Claude Code command-line tool, installed for your server user, driven headlessly one turn at a time. The brain is the mind; the reasoner is the hands; CC is where you meet them.

It is off by default. A brain shows the CC tab only when its owner switches it on and installs the box side. Nothing about the reasoner ships inside the brain's containers, and no vendor account is ever ours: the reasoner runs on your account, on your server.

## What you need

- A running brain, this version or later, that you can reach over SSH as the brain user (the provisioner's default user is `hbar`; it has sudo).
- One of: a Claude subscription, or an Anthropic Console account billed per use.
- Ten minutes.

## Install, once

1. On your server, in the brain directory, run the box side:
   ```
   bash scripts/cc/install.sh
   ```
   It installs a small web terminal and the reasoner CLI for your user, starts two services on localhost, adds two routes to the console's Caddy configuration behind the console password, and copies the brain's own API key into a private file so the bridge can search your memory. It does not touch your .env, your containers, or your database. It prints what it did and where the backups are.
2. Switch the tab on. Add one line to the brain's .env (it is root-owned on most brains, so with sudo):
   ```
   echo BRAIN_CC_ENABLED=true | sudo tee -a .env
   ```
3. Restart the api so it reads the flag: press Update in the console, or on the server `docker compose up -d api`.
4. Open the console. CC is now the first tab. Connect a reasoner: paste your own Anthropic API key (it stays on your server, billed to your account), or sign in with your own Claude subscription: the card opens a panel that runs the provider's own sign-in and nothing else (open the link, sign in, paste the code where it asks, close the panel). The panel is the box's terminal styled like the console, so the code lands in Claude Code itself on your server. Nothing about your account passes through the console page. On a brain you operate yourself you may enable the page-driven subscription sign-in with `CC_SUBSCRIPTION_PROXY=1` in the bridge env file; it is off by default because Anthropic's terms do not allow a third party to pass a subscription code through its own page.
5. Say hello. The first turn starts a thread that continues across reloads and restarts until you press "new thread".

No browser on the box, no terminal either: on any machine where you are signed in to the reasoner CLI, run `claude setup-token`, copy the token it prints, then on the box run `bash scripts/cc/set-token.sh` and paste it when prompted. The token goes into the bridge's protected env file and both the bridge and the terminal door use it. It is your token, on your server; it never enters a repo.

## Threads

Every CC conversation is written into the brain's own chat record as it happens, as a session named "CC: …" after your first sentence, with the reasoner's answers and a line for every proposed or auto-run write. So your threads show in the Chat tab's session list, travel with the export, and are there for consolidation. The CC page shows the current thread again after a reload, and a "threads" button lists earlier ones to switch back to. "New thread" starts a fresh conversation for both the reasoner and the record.

Several conversations at once (2026-09-28): each thread answers on its own, up to `CC_MAX_RUNS` (3) at a time. "New thread" and switching work while another thread is answering; the list marks which ones are "answering" or "waits for you", and the footer says "another conversation is answering". A turn in flight can be followed from anywhere: another tab, the phone, or a switch back to that thread; the bridge replays what happened so far (`GET /cc/live?thread=`) and streams on. A card lands in the conversation that raised it. A message sent while a thread answers is not refused (2026-10-09): the bridge queues it, the page shows it as "queued" with a cancel link, and the bridge starts it as the thread's next turn the moment the running one ends, in the order sent (up to 20; `POST /cc/queue`, `/cc/queue/cancel`, `GET /cc/state?thread=`). It works with the page closed. A message is not injected into a running turn: the reasoner takes one prompt per process. The status line reads the bridge's own state (turn running, steps, subagents, elapsed), not just what the page started.

Every text block stays (2026-10-09): each piece of prose the reasoner writes in a run is its own bubble, in order, and a later one never replaces an earlier one; when a background subagent hands back, a small line "agent report received" marks it (it is not your message) and what the reasoner writes after it is a new bubble. The brain's record keeps the same pieces, so a reload shows them. Selecting words in a message is left exactly as dragged: the markdown of a message is no longer rebuilt on every refresh of the page.

Remarks in the margin (2026-09-28): select words in one of the brain's messages and a gold "remark" button appears; it opens a note beside that message (below it on a narrow screen) with the quoted span and a box for your remark. Make as many as you like across messages; they wait, even across a reload, per thread in your browser. The composer says how many go with your next message, and Send delivers your line plus a block the reasoner reads: which message, the exact span, your remark. Send with an empty composer sends the remarks alone. The conversation's width is yours too: "narrow / wide / full width" in the footer.

The shape of threads (2026-09-30): the list is grouped by day (today, yesterday, then the date), with pinned threads in their own group on top. Each row has three small links: "rename" (an inline box; Enter saves, Escape cancels; up to 80 characters, and the brain's own chat session takes the new name too), "pin" or "unpin", and "archive". Archived threads leave the list; a footer line "N archived · show" brings them back with "unarchive" on each. The current thread's name sits under "Talk to your brain" with its own "rename". The bridge keeps all of this in `threads.json` (`POST /cc/threads/update` with `brain` and any of `title`, `pinned`, `archived`; `GET /cc/threads?archived=1` includes the archived ones). Nothing is deleted: archive hides, it does not remove the brain's record.

If step 4 fails, the old way still works: the terminal at `https://console.<your brain>/claude/` runs the same CLI; `claude auth login` there does the same thing.

## What it can and cannot do

- It reads freely: the brain's persona, the nearest chunks of the brain's memory for each message, the files in the brain repository on the server, and the mirror of your own repositories if you set one up.
- It writes only with your click. Connected apps go through One with a Send card. Files and commands on the box itself go through an Allow card (see "Hands on the box"). The memory write path stays the brain's governed one (propose, approve, ingest).
- Memory text is handed to the reasoner as remembered content and declared as such, never as instructions. The same rule the brain's own chat uses.
- One turn at a time per conversation. You can type while a turn runs; messages queue and send, in order, when the turn ends.
- Speed: a turn that memory can answer takes a few seconds. A turn where the reasoner has to search files or look things up takes longer, twenty to thirty seconds on a small ARM box, because each lookup is a round trip to the model. The text streams as it forms, so you read while it works.

## The home screen

With CC switched on, the console opens on CC: "/" is the conversation, and the dashboard moves to /dashboard. The tab bar folds into one "everything" button at the top right that lists every tab. Until the first-use steps are done, the brain says what is left in one line each, with a link that opens the right screen beside the conversation. When a screen would help, the reasoner can summon it the same way: the knowledge browser, an app, settings, the update view slide in as a pane on the right (an overlay on narrow screens) and go away with one click. Pages shown as panes hide their own navigation. Nothing else changes: every page still has its own address.

## The memory graph

"Show me my mind" opens the graph beside the conversation (also under "everything" as Graph). Every dot is a document the brain remembers, sized by how much of it the brain holds, coloured by layer; lines join documents that mean similar things (nearest neighbours by the mean of their chunk embeddings, from `GET /graph`); rings mark what the brain just retrieved for your current turn. Hover names a document, click shows its neighbours, and "ask the brain about this" drops a question into the conversation. The graph is computed from what already exists and cached for five minutes.

## Hands: connected apps through One

CC can reach the world through One (https://www.withone.ai/), a service that holds the OAuth tokens for apps like Google Calendar and Gmail and proxies the calls. The brain owner sets it up on the box: install One's CLI (`npm i -g @withone/cli`, Node 18 or newer), put `ONE_SECRET=<your One API key>` into `~/.cc-bridge/env`, and run `bash scripts/cc/install.sh` again. The installer separates looking from doing: the reasoner may list connections, search actions and read their schemas without restriction, so it can find any action, but it may run only `one-read`, a small wrapper that executes from a directory where One's CLI allows GET only. It has no general execute command. Do not put a read-only `.onerc` into the brain directory: it hides write actions from lookups and the reasoner can then never propose one. In One's dashboard set every connection to Read only. `/cc/health` then reports `"hands": "one"`, and the reasoner reads your calendar or mail when you ask.

What One receives: the requests the reasoner makes and their responses, and a log of each call in One's dashboard. Not the reasoner's prompts, not the brain's memory. You can revoke One in your Google account at any time.

## Writes: the permit gate

The reasoner never executes a write. When you ask for one ("create an event tomorrow at ten", "send this email"), it does the lookup and then proposes the action. The proposal appears in the same chat bubble as a card: platform, action, target in one line, and two buttons, Send and Cancel. Nothing is sent until you press Send.

Behind the card is permitd (https://pypi.org/project/permitd/), a small library from this constellation: your click mints a permit that is signed, single-use, bound to the exact arguments, and valid for fifteen minutes. The bridge then runs that one action through One from a separate directory that allows writes; the reasoner's own directory never does. Every proposal, approval, cancellation, execution and refusal lands in `~/.cc-bridge/permitd-audit.jsonl`, a hash-chained log you can verify with `permitd audit --verify`.

Two extra protections come with it. An egress guard refuses any proposal whose arguments look like a credential, before a card is even shown. And if the instruction to write came from content the reasoner read, an email or a note, rather than from you, it is told not to propose and to say so.

For the write to actually succeed, the connection in One's dashboard must allow it. Prefer a Custom grant with exactly the action you want (for example "create event"), not Read and write, and never full access.

If you reload the page with a card still waiting, it comes back at the top of the thread until you decide.

Once you trust a kind of write, tick "don't ask again for this action" on its card before pressing Send. From then on that exact action on that platform runs without a card: the reasoner still proposes it, the bridge approves and runs it, and the audit still records every one. The footer shows how many actions run without asking; open the list and press "ask again" to take one back. Nothing runs without asking unless you ticked it. The list lives in `~/.cc-bridge/auto.json`.

In the judged posture (below) a proposed write is also read against your request before the card: the card shows "on request" and "risk". The judge never sends a write by itself, a write leaves the machine; what it can do is hold one. A remembered write that the judge does not see in your request comes back as a card that asks, with a line saying why. That is the guard against an instruction inside an email or a document the reasoner read: it can make the reasoner propose, it cannot make a remembered write run. (Sent to the judge: your request, the platform, the action, the one-line summary, and the fields of the write with the first characters of each; not the whole body. 2026-09-23.)

## Where things live on the server

| piece | place |
|---|---|
| bridge code | `scripts/cc/cc-bridge.py` in the brain repo (updated by the Update tab; restart with `sudo systemctl restart cc-bridge`) |
| bridge service | `cc-bridge.service`, user = brain user, 127.0.0.1:7682, base `/cc` |
| terminal service | `claude-tab.service`, 127.0.0.1:7681, base `/claude` |
| reasoner CLI and its credentials | `~/.local/bin/claude`, `~/.claude/` of the brain user |
| bridge state (thread id) and the api key copy | `~/.cc-bridge/state.json`, `~/.cc-bridge/env` (mode 600) |
| permit gate | `~/.cc-bridge/venv` (permitd), `~/.cc-bridge/permitd.db`, `~/.cc-bridge/permitd-audit.jsonl`, `~/.cc-bridge/exec/.onerc` (the only place writes are allowed) |
| console routes | two `handle` blocks in `/etc/caddy/Caddyfile`, inside the console's basic-auth block; a dated backup sits beside it |

- `scripts/cc/cc-permit-hook.py`: the permission hook the reasoner runs; `/usr/local/bin/brain-write` and `/etc/sudoers.d/cc-bridge`: the root verbs, when the box lane is on.

## What the reasoner may do, visible

Settings has a CC section that shows, read-only, what the bridge reports: which reasoner, how it is signed in, the exact tool list, memory on or off, the workshop mirror, the hands and whether writes need your Send, the write gate and how many actions run without asking. Two audit files sit on the server: `~/.cc-bridge/turns.jsonl`, one line per turn with sizes and timings and never content, and `~/.cc-bridge/permitd-audit.jsonl`, every proposed, approved, denied and executed write, hash-chained.

## Accounts and terms, plainly

The reasoner runs on the brain owner's own account. Anthropic's terms (read 2026-09-19, quoted in the operator's legal notes) permit hosting the unmodified Claude Code binary in a product when every end user authenticates with their own API key or their own subscription and nobody pays, resells or intermediates usage for them. They do not permit a third party to offer Claude.ai login inside its own page or to pass subscription credentials or session tokens through. That is why the card offers the API key first and sends a subscription to the terminal door. If you operate brains for other people: their key or their sign-in, never yours, and never a token you store for them. The hosting party accepts Anthropic's Commercial Terms.

## What you see while it works

Text appears as the reasoner writes it. Under the bubble, the last few things it did (a file read, a One lookup, a command) show as they happen. When the answer is complete the footer says how long it took, which model answered, how many tokens went in and out, and how many steps the turn had. Tokens in include the cached prompt; on a subscription this is not a bill, on an API key it is what you pay for.

## Slash commands and the model

Type a slash in the box: `/new` starts a thread, `/model sonnet` or `/model opus` (or a full model id) picks the reasoner's model from the next turn on, `/model` alone returns to the default, `/posture cards` or `/posture auto` sets how much your own box asks, `/pane /graph` opens a pane, `/help` lists these. Any other slash command goes to the reasoner as typed, so its own custom commands work. The interactive CLI's menus (`/resume`, `/compact`, `/config`) do not exist in a headless turn; threads and the new-thread button are the equivalents here. You can type while a turn runs; the next message queues and sends when the turn ends.

## Hands on the box

In plain words: the reasoner in your chat can work on your server the way it would on a laptop. It can read any file it is allowed to see, change files, and run commands. The difference from a laptop is that every change and every command first appears as a card in your chat, with the exact file name or the exact command, and nothing happens until you press Allow. Refuse, and the reasoner is told you refused and carries on without it. Tick "don't ask again" on a card and that kind of action (for example, everything that starts with `git`, or edits inside one folder) runs without a card from then on; the list of what you allowed sits under the chat and each entry has an "ask again" link. Dangerous kinds (`rm`, `sudo`, pipes, redirects, `chmod`) never offer the tick.

What it can never do, card or no card: it runs as a plain user without sudo. So it cannot read your brain's secrets file, cannot touch the database, Caddy, systemd or Docker, and cannot change how the console is protected. The few root actions that are useful for looking after a brain are on a fixed list the installer writes: restart the bridge or the terminal door, read service status and logs, run the brain's Update, and write a file into the brain repository through a helper that refuses secrets and git internals. Each of those also raises a card. Anything else with sudo simply fails.

Your repositories can live on the box too: set `CC_WORK_DIR` in the bridge env to a folder holding writable clones (one per repository, cloned by the bridge user with a token scoped to those repositories). The reasoner then builds there, pulls before editing, and pushes only when you say push. The read-only mirror stays for looking things up.

Three postures, chosen by the owner with `/posture` in the chat. `cards`, the default: every edit and command that would need permission asks. `auto`: Claude Code's own classifier decides ordinary edits and commands, the same way it does on a laptop, and cards remain for anything with sudo and for every write in a connected app. `judged` (2026-09-22): before a card is shown, a TypeSafe System One model answers three typed questions about the action, is it safe to run unasked, does it serve your last request, how severe is the worst outcome; above the thresholds (0.80, 0.60, at most "mild"; tuned 2026-09-26 on the first judgments) it runs and the card shows the numbers; below, the card asks and still shows them. sudo always asks. Needs `TYPESAFE_API_KEY` in the bridge env; without it, or when the judge does not answer, the bridge asks. The model judges; the gate consents and records. Auto and judged are for your own files on your own box; on a brain you run for someone else, leave cards on.

How it works, for the record: Claude Code fires its own PermissionRequest hook whenever a tool call would need permission. The hook (scripts/cc/cc-permit-hook.py) posts the call to the bridge and waits. The bridge mints a permit, shows the card inside the live answer, and answers the hook when you click. The reasoner's own tool then performs the action. Same permit gate, same hash-chained audit as the One writes. This lane is on only when the bridge runs as a user without sudo (`CC_BOX=1`, set by the installer after harden-user.sh); with a sudo user it stays off, because a reasoner with general sudo is the whole server, card or no card.

## The world in the laptop's shape

Two ways to give the reasoner the owner's repositories. The simple one: `CC_WORLD_DIR` a read-only mirror and `CC_WORK_DIR` a folder of writable clones, one per repository. The other (2026-09-24): both variables naming one writable checkout of the owner's world, with the repositories placed inside it exactly as on their own computer (`systems/<system>/repos/<repo>`, mapped by their registry). Then the reasoner runs with the world as its working directory (the world's CLAUDE.md, skills and hooks load, and a memory directory shared with the owner's other Claude sessions at mind/claude), the drawer shows one `world`, the reasoner is told the layout is the one it already knows, "go into that system" means the same folder on both machines, and the 5-minute pull refreshes every nested clone that has no local changes. The hbar.world script that does the placing is `ops/2026-09-24_world-shape/shape-world.sh`.

## Filing: the desk and the archive

`out` (what the reasoner made) and `in` (what you gave it) are the desk. The world is the archive. On anything under them the Files pane offers "file this", and the chat has `/file <path> [where]`: the reasoner moves the artifact into the world where it belongs and commits there, never pushes, and says in one line where it went. Text is committed at its place (a system's ops/, a dated note under ops/, a discussion); binaries are never committed: they go to the media archive (or the owning system's archive/) with a short committed note beside the system that names them. When the place is not clear it asks with two options. Added 2026-09-24; needs the world in the laptop's shape.

## Stop and interrupt

While a turn answers: "stop" (or Esc, or `/stop`) ends it. What it said so far stays as the reply with "(stopped by you)", and every step it finished stands; the next message resumes the same thread from the reasoner's own session. "send now" (or Cmd/Ctrl+Enter) is the terminal's interrupt, one turn at a time: your message is queued and the turn is stopped, so the message goes in the moment the turn ends. Enter alone still queues for when it finishes. From Telegram, `/stop`. The bridge route is `POST /cc/stop` with `thread` or `run`.

## Side by side

`/panes` (the "side by side" button in the CC header) shows one to four conversations at once, like terminal windows. Each pane is the CC page itself at `/talk` (the same page; Caddy sends a fresh load of `/cc` to the bridge), pinned to one thread with `/talk?pane=1&thread=<brain id>` (or `thread=new`); a pinned page never calls `/cc/threads/switch` or `/cc/new`, so panes do not pull each other or the phone. Choose a pane's conversation from its title, "new" starts a fresh one, "alone" opens it full width, × closes the pane (the thread stays in threads). The layout is kept per browser. The box answers `CC_MAX_RUNS` conversations at once (3 by default); a fourth pane's turn waits.

## Files, jobs and attachments

Files: the drawer lists Files, and the reasoner opens it as a pane when it makes something. Five places: out (what the reasoner made, under ~/out/<date>/), in (what you attached), work (your repositories), world (the read-only mirror), brain (the brain's own code). Audio and video play in the pane and seek; images, PDFs and text show; anything downloads; "ask the brain" drops the file's path into the chat. Text files inside the world, out and in can be edited in place (2026-09-28): "edit" or a double-click opens the text in a box, Cmd-S or "save" writes it through the bridge (`POST /cc/files/write`), which refuses .env, .git, secrets and the brain repo; a file changed on disk since you opened it is a conflict with a reload link, never a silent overwrite.

Links and views (2026-10-09): every absolute path under an in/ or out/ folder in a message, yours or the brain's, is a link that opens in the Files pane (images shown there; hover an image path for a small preview), and an image chosen in the composer shows a thumbnail on its chip. A reference in an answer (`ops/x.md`, a bare name, `X.MD`, with trailing punctuation, `:12`, `#heading`, a `world/` prefix, a path from another machine, or a markdown link to a file) is found by `Files.locate` (cc_extras.py): it cleans the text, tries every root, ignores case, then searches by name in the world, work, in, out and the brain (bounded, never outside a root). The md is the input, a visual is the output: opening a .md in the Files pane shows `<name>.view.html` (or `<name>.md.view.html`) beside it first, in a sandboxed frame without forms, with a "source" toggle; with no sidecar the pane draws a clean view itself (headings as a collapsible tree, tables as sortable grids, checklists as toggles whose state stays in your browser, links and file references as clickable nodes). Notes with a sidecar carry a small "view" badge in the file list.

Jobs: a command that may run longer than a few minutes is started with `cc-job run -C <dir> -t "<title>" -- <command>`; it runs on after the turn ends, logs to ~/out/jobs/<id>.log, and the page shows "n jobs running" under the chat. When one finishes, a small card appears with the last lines and a button to have the brain read the log. Jobs never run sudo. `/jobs` lists them.

Attachments: the attach button, or drop files on the box where you type. They upload to ~/in/<date>/ on your server and the message names their paths; the reasoner reads them from there. Up to 50 MB per upload.

## Tool packs (MCP servers)

The reasoner sees no MCP servers by default, not even your own account's connectors: the bridge starts it in strict mode with an empty server list. To attach a tool pack, for example the ableton-systems or numa-systems plugin installed for the bridge user, write an MCP servers file and name it in the bridge env as `CC_MCP_CONFIG=/home/cc/.cc-bridge/mcp.json`; restart the bridge. Only the servers in that file appear; strict mode stays on. Keys those servers need go in `~/.cc-bridge/env` (the owner types them on the box, never in a chat) and reach the servers through the reasoner's environment. Free tools you list in `CC_TOOLS` run without a card; anything else, including paid generation, raises a card every time. Settings shows which packs are attached. Added 2026-09-22.

## Memory follows the world

If something on the box proposes documents to memory on its own (for example a reconciler that watches a mirror of the owner's repositories and proposes new or changed files every half hour), the page shows "n documents wait for your approval" and opens Knowledge, where you approve or reject each one. The reasoner never approves. What memory holds stays a decision of the owner.

## The brain speaks

With `ELEVENLABS_API_KEY` in the bridge env (entered on the box, never in the page), the footer shows "voice off"; click it, or type `/voice on`, and every answer is read aloud as it finishes. "listen" under any answer replays it; "stop" stops it. The speech is made through the bridge, so the key stays on your server. Code is skipped ("code omitted"), links become "a link", and a long answer is read up to a cap and then says the rest is on the screen. Speech is made a paragraph at a time, so a long answer starts within a couple of seconds. `/voice list` shows the voices on your ElevenLabs account; `/voice use <name>` chooses one (remembered; the footer shows it). The model is ElevenLabs' natural one (`CC_VOICE_MODEL=eleven_multilingual_v2`; `eleven_flash_v2_5` is faster and flatter), `CC_VOICE_MAX_CHARS` caps the length. The voice is the brain's own, a stock voice until you choose; it is not a copy of your voice. Added 2026-09-23, made natural 2026-09-24.

A free voice, on your own machine (2026-09-30). Beside ElevenLabs the bridge speaks and hears through a voice spoke: two OpenAI-compatible servers you run on a machine of your tailnet, Kokoro for speech and faster-whisper for transcription, each a small container with no account and no key. Set `CC_TTS_URL` (for example `http://100.84.44.71:8880/v1/audio/speech`) and the answers are read by the spoke; `CC_TTS_VOICE` picks the Kokoro voice (`af_heart` by default; `/voice list` shows the stock eight and `/voice use <name>` chooses one, remembered), `CC_TTS_MODEL` is `kokoro` and `CC_TTS_FORMAT` is `mp3`. Set `CC_STT_URL` (for example `http://100.84.44.71:8000/v1/audio/transcriptions`) and recorded clips and Telegram voice notes are transcribed there, with `CC_STT_MODEL` (`Systran/faster-whisper-small` by default; the ElevenLabs model is `CC_ELEVEN_STT_MODEL`). `CC_VOICE_BACKEND` decides: `auto`, the default, takes the spoke while its URL answers within two seconds (checked every thirty) and falls back to ElevenLabs when the key is set; `spoke` and `eleven` force one. The spoke costs nothing per character, the audio never leaves your tailnet, and ElevenLabs stays optional: leave the key out and the spoke is the only voice, keep it and it is the fallback when the spoke's machine is off. `/cc/health` says which is speaking in `voice_backend` (`spoke`, `eleven` or null) and which is hearing in `transcribe_backend`; the footer shows the voice's name either way.

## The font of the conversation

Under "details" in the footer, "font" (2026-09-30) opens a row of the six fonts the Chat tab offers, each name drawn in its own font so the choice is seen before it is made: System sans, Inter, Lora, Crimson Pro, DM Mono, JetBrains Mono, and "default", the theme's display font. The pick applies to the conversation column only and is remembered in this browser (`cc.font`); nothing is sent to the box, and the default is unchanged until you choose.

## Talking to the brain

Press "talk" beside "attach", or type `/talk`, and speak. The words appear in the composer as you say them; a pause of about a second and a half ends the run, or press "stop". What you said stays in the composer until you send it. Chrome and Safari on a phone recognise speech in the browser, so nothing you say leaves the phone. A browser without that (Firefox) records a clip instead and the bridge transcribes it through ElevenLabs speech-to-text (`POST /cc/transcribe`, the same key as the voice, at most 10 MB, nothing kept on the box); without the key the button says so in one line. "hands-free" in the footer (or `/talk free on`) makes a conversation that needs no touch: what you say sends by itself, and once the answer has finished speaking, listening starts again. The brain never listens while it is speaking; it would hear itself. Hands-free is remembered per browser. Added 2026-09-27.

## The technical surface

"System" in the drawer (order beside Update) shows the box in numbers, refreshed every minute: disk, memory, load, uptime, backups and the memory store from the api (`GET /admin/system`, read inside the container through /proc, the bind-mounted brain directory and the Docker socket); containers and images with what is reclaimable; the running and previous commit; local inference and the spokes; and, when CC is on, what only the host can see through the bridge (`GET /cc/system`): the tailnet and its peers, established connections and listening ports, failed services, the bridge's own units, permits and judgments recorded. Each tile carries a level against fixed thresholds (disk 80/90%, memory available 15/7%, load 1.0/2.0 per core, backup age 2/7 days, 5 GB reclaimable), and the first crossed threshold shows as one line in the chat footer, linking here. Nothing on the page changes anything. Added 2026-09-24 after the disk was found at 85% by accident.

## The guide, in the console

"Guide" in the drawer (and `/guide` in the chat, or the reasoner opening it when you ask how things work) shows this document inside the console, and a seven-step tutorial that checks itself: connect a reasoner, ask something, see what it makes, give it a file, allow a card, start a job, choose a posture. Each step turns done when your brain has seen it happen; nothing is required.

## The terminal, in the console

With CC on, the drawer lists Terminal: a shell on your box as its owner, framed inside the console behind the same password. The reasoner can also open it as a pane. It is the same door the sign-in uses. Nothing you do there is seen by the reasoner. After the first install, nothing about CC needs a laptop terminal: the bridge restarts itself when an Update changes it, and the installer reruns itself when an Update changes the installer (log in ~/.cc-bridge/install.log). Work clones, if set up, fast-forward every five minutes; a clone with local changes is left alone.

## Running the bridge without sudo

On provisioned brains the brain user has sudo, so a reasoner running as that user is a full administrator of the box. `bash scripts/cc/harden-user.sh` moves the bridge to a plain user named cc: its own home, its own reasoner sign-in, the permits and audit moved over, the units rewritten. The terminal door stays the brain user's. Run it with `--copy-login` only on a brain you operate yourself, to copy your own reasoner sign-in to the new user; otherwise sign the new user in with your API key from the CC page or with `set-token.sh`. The installer remembers the bridge user afterwards.

## Side by side: the stream is the pane

`/panes` tiles one to four conversations. Reading space (2026-10-06, from the operator at four panes: "not enough space to read"): each pane has one header line (its number, a state dot for idle, answering or waiting on your yes, the title, which renames on a click, what it is doing, and one menu: threads, new thread, export, alone, details, wide, rename, close) and one composer line that grows as you type, with attach, talk, stop and send as small buttons; everything between is the conversation, opened at its latest exchange. What every pane used to repeat under its composer is shown once in the page's top bar: system warnings, voice, hands-free, the actions that run without asking, files. A pane shows only its own state; the lines about tools, memory, usage, the account and the latest files open under "details" from its menu. "wide" shows one pane alone while the others keep running. On a laptop screen of 1440 by 900 the stream takes about 85 % of a pane: about eleven lines at four panes, about twenty-six at two (it was two lines at four panes). The single conversation at `/talk` is unchanged.

## Mission control: one board for all running work

`/board` (2026-10-06, the operator's idea of 2026-10-05: displays for parallel work, not terminal-styled) shows one tile per run, assembled by the bridge from what it already tracks, with no new run system: the run registry (turns in flight and just finished, with their events and waiting cards), the turn audit, the threads list, the jobs registry and pending permits. `GET /cc/board` returns the tiles; `POST /cc/board/dismiss {key}` takes a finished or failed one off the board (kept in `~/.cc-bridge/board.json`). A tile carries the task in one line, the state as a colour and a word (waiting on you, failed, answering, done), elapsed time, tokens or cost for the day, the count of steps and of subagents the turn fanned out to, and the last meaningful line: the latest tool step or sentence while it runs, the opening sentence of the answer once done. A card that waits for your yes sits on its tile with Allow and Refuse, so it can be answered from the board. A finished tile lists the links its answer named (web addresses, files under out, in and the world) and the pane it opened. A click opens the conversation alone at `/talk?thread=`; a job's tile opens its log. Order: waiting on you, failed (pinned until dismissed, up to a week), answering, done (the last 24 hours). The page asks once every three seconds and not at all while its tab is hidden; on a phone the tiles stack in one column. Reached from the "board" button on the conversation page and from side by side. Not yet on the board: runs on other machines (a terminal chat on the laptop); they can join later through the same registry.

## Telegram: the phone talks to the hands

A second bot, the bridge's own (2026-09-29): create it with @BotFather, put its token into the bridge env with `scripts/cc/set-env.sh CC_TELEGRAM_TOKEN`, and write to it once; the first chat that writes becomes the owner (or set `CC_TELEGRAM_OWNER`), everyone else is told the brain is private. The bridge long-polls Telegram, so there is no webhook and no public route. A message is a turn on the "Telegram" thread, which shows in the console's threads list and can be followed there; `/new` starts another, `/status` says what is running. Voice notes are transcribed (the voice key) and echoed as "heard: …" first; photos, videos and files land in ~/in/<date>/ and the message names them. A card arrives as "May I? …" with Allow and Refuse buttons; what the posture allows by itself is reported as "did without asking". `CC_TELEGRAM_APPROVE=0` takes the buttons away: cards raised from the phone wait for the console, so a stolen Telegram session can ask but never approve. Turn on Telegram's Two-Step Verification either way. The reply comes back in pieces under Telegram's limit, then the tool steps. Telegram's bot traffic is not end-to-end encrypted; Signal has no official bot door and is a later day's work through the same turn path.

## Two users: the bridge and the hands

Live on hbar since 2026-09-29 (rehearsed on e2e the day before). Until 2026-09-27 the bridge and the reasoner ran as one user, so the reasoner could read the gate's signing secret and call the bridge's own decision routes on localhost. Now the box can be split: the bridge keeps its state, keys and tokens in its own home, closed to the hands; the reasoner and its jobs run as a second user (`hands`) through sudo, with a sanitized environment that carries only what the permission hook and cc-job need; and every page route of the bridge requires an operator token that the console's proxy (Caddy) adds to requests that passed the owner's login, from a root-only environment file the hands cannot read. `scripts/cc/split-hands.sh` does the migration once (user, moves, modes, sudoers, tokens, Caddy, units) and `split-hands.sh verify` runs the four checks: the hands cannot read the bridge's state nor the brain's .env, the bridge reads the hands' world, a decision without the token is refused. `CC_HANDS_USER` empty keeps the single-user mode for boxes not yet migrated. Two things the first real run taught: the brain's `.env` can be left root-owned and world-readable by the Update helper (the script now closes it, with the backups), and the reasoner's `~/.claude.json` must follow to the hands or it starts signed out; the bridge asks sign-in status, signs in and out as the hands. What the hands still hold by necessity: their own reasoner login, the packs' keys (the packs run as the hands), the GitHub token for pushes, and the ask token (which only lets them ask).

## Security shape

- The bridge and the terminal bind to localhost. The only way in is the console password over HTTPS.
- The terminal door runs as the brain user, who has sudo on provisioned brains: it is a full shell on your box behind the console password. The bridge can run as a plain user (harden-user.sh). Read docs/SOVEREIGN_SECURITY_GUIDE.md.
- Audits: one line per turn and one per write or allowed action, all on the box, none with content.
- Root for the bridge user is the fixed list in /etc/sudoers.d/cc-bridge, nothing else; the write helper /usr/local/bin/brain-write refuses .env and .git.

## Turn it off

```
sudo systemctl disable --now claude-tab cc-bridge
sudo cp /etc/caddy/Caddyfile.bak.<stamp> /etc/caddy/Caddyfile && sudo systemctl reload caddy
```
Remove `BRAIN_CC_ENABLED` from .env and restart the api; the tab disappears. `claude auth logout` forgets the account; removing `~/.claude` and `~/.cc-bridge` forgets everything else.

## Troubleshooting

- The CC page says the bridge is not answering: on the server, `systemctl status cc-bridge`; run the install script again.
- Terminal at /claude/ shows 404: the Ubuntu ttyd package's own service took port 7681. The install script disables it; re-run it.
- Sign-in never shows a link: `journalctl -u cc-bridge -n 50`; try the terminal door.
- Answers say "the reasoner is not signed in": sign in again from the CC page.
- Health shows memory off: `~/.cc-bridge/env` has no `BRAIN_API_KEY`; the install script fills it from .env when it can.
