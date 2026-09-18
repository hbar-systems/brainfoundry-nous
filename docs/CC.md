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
4. Open the console. CC is now the first tab. Press one of the two sign-in buttons, sign in on the page that opens, paste the code back, press Finish. That is the only time you see anything about the account.
5. Say hello. The first turn starts a thread that continues across reloads and restarts until you press "new thread".

If step 4 fails, the old way still works: the terminal at `https://console.<your brain>/claude/` runs the same CLI; `claude auth login` there does the same thing.

## What it can and cannot do

- It reads: the brain's persona, the nearest chunks of the brain's memory for each message, and the files in the brain repository on the server. Read, Grep, Glob, nothing else.
- It does not write. Not to memory, not to files, not to the network. The memory write path stays the brain's governed one (propose, approve, ingest).
- Memory text is handed to the reasoner as remembered content and declared as such, never as instructions. The same rule the brain's own chat uses.
- One turn at a time per brain. A second message while one runs is refused, not queued.
- Speed: a turn that memory can answer takes a few seconds. A turn where the reasoner has to search files takes longer, twenty to thirty seconds on a small ARM box, because each search is a round trip to the model.

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

## Accounts and terms, plainly

The reasoner runs on the brain owner's own account. A Claude subscription is personal: its login may not be shared, resold, or bundled into a product price, and CC does not do any of that. If you operate brains for other people, each brain signs in with that person's own account, or uses that person's own Console API key; you never sign in with yours, and you never fold a subscription into what you charge. When in doubt, the Console door is the plain one: per-use billing to the owner's own account. Read the current terms before you rely on either.

## Security shape

- The bridge and the terminal bind to localhost. The only way in is the console password over HTTPS.
- The bridge runs as the brain user. On provisioned brains that user has sudo, so the terminal is a full shell on your box. Treat the console password accordingly, and read docs/SOVEREIGN_SECURITY_GUIDE.md.
- Planned hardening (tracked as 0.12.0 in the operator's plan): a separate credential for CC, a user without sudo for the bridge, one audit line per turn, and an explicit tool list as a setting.

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
