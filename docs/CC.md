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

If step 4 fails, the old way still works: the terminal at `https://console.<your brain>/claude/` runs the same CLI; `claude auth login` there does the same thing.

## What it can and cannot do

- It reads: the brain's persona, the nearest chunks of the brain's memory for each message, and the files in the brain repository on the server. Read, Grep, Glob, nothing else.
- It does not write. Not to memory, not to files, not to the network. The memory write path stays the brain's governed one (propose, approve, ingest).
- Memory text is handed to the reasoner as remembered content and declared as such, never as instructions. The same rule the brain's own chat uses.
- One turn at a time per brain. A second message while one runs is refused, not queued.
- Speed: a turn that memory can answer takes a few seconds. A turn where the reasoner has to search files takes longer, twenty to thirty seconds on a small ARM box, because each search is a round trip to the model.

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

## What the reasoner may do, visible

Settings has a CC section that shows, read-only, what the bridge reports: which reasoner, how it is signed in, the exact tool list, memory on or off, the workshop mirror, the hands and whether writes need your Send, the write gate and how many actions run without asking. Two audit files sit on the server: `~/.cc-bridge/turns.jsonl`, one line per turn with sizes and timings and never content, and `~/.cc-bridge/permitd-audit.jsonl`, every proposed, approved, denied and executed write, hash-chained.

## Accounts and terms, plainly

The reasoner runs on the brain owner's own account. Anthropic's terms (read 2026-09-19, quoted in the operator's legal notes) permit hosting the unmodified Claude Code binary in a product when every end user authenticates with their own API key or their own subscription and nobody pays, resells or intermediates usage for them. They do not permit a third party to offer Claude.ai login inside its own page or to pass subscription credentials or session tokens through. That is why the card offers the API key first and sends a subscription to the terminal door. If you operate brains for other people: their key or their sign-in, never yours, and never a token you store for them. The hosting party accepts Anthropic's Commercial Terms.

## What you see while it works

Text appears as the reasoner writes it. Under the bubble, the last few things it did (a file read, a One lookup, a command) show as they happen. When the answer is complete the footer says how long it took, which model answered, how many tokens went in and out, and how many steps the turn had. Tokens in include the cached prompt; on a subscription this is not a bill, on an API key it is what you pay for.

## Slash commands and the model

Type a slash in the box: `/new` starts a thread, `/model sonnet` or `/model opus` (or a full model id) picks the reasoner's model from the next turn on, `/model` alone returns to the default, `/pane /graph` opens a pane, `/help` lists these. Any other slash command goes to the reasoner as typed, so its own custom commands work. The interactive CLI's menus (`/resume`, `/compact`, `/config`) do not exist in a headless turn; threads and the new-thread button are the equivalents here. You can type while a turn runs; the next message queues and sends when the turn ends.

## Running the bridge without sudo

On provisioned brains the brain user has sudo, so a reasoner running as that user is a full administrator of the box. `bash scripts/cc/harden-user.sh` moves the bridge to a plain user named cc: its own home, its own reasoner sign-in, the permits and audit moved over, the units rewritten. The terminal door stays the brain user's. Run it with `--copy-login` only on a brain you operate yourself, to copy your own reasoner sign-in to the new user; otherwise sign the new user in with your API key from the CC page or with `set-token.sh`. The installer remembers the bridge user afterwards.

## Security shape

- The bridge and the terminal bind to localhost. The only way in is the console password over HTTPS.
- The terminal door runs as the brain user, who has sudo on provisioned brains: it is a full shell on your box behind the console password. The bridge can run as a plain user (harden-user.sh). Read docs/SOVEREIGN_SECURITY_GUIDE.md.
- Audits: one line per turn and one per write, both on the box, both without content.

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
