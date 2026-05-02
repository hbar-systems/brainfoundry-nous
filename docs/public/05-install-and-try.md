# Install and try

This document walks through trying a brainfoundry brain from a visitor's perspective — installing the public `nous` CLI, holding a conversation with the demo brain, and seeing how writes are gated — and then shows the two ways to get a brain of your own: self-host the open-source template, or buy a spawn from the provisioner. Brain owners get their own branded CLI (`alice`, `bob`, `carol`) pre-configured to their node.

## Two kinds of CLI, one source

brainfoundry ships two kinds of command-line client:

- **`nous`** — the public CLI anyone can install. Its default endpoint is `https://nous.brainfoundry.ai`, the public demo brain. Purpose: let strangers talk to the demo brain about what brainfoundry is, how it works, and how to get one. Reads only — strangers cannot write to someone else's brain, including the demo.
- **Branded per-brain CLIs** — `alice`, `bob`, `carol`, one per owner. The provisioner generates each owner's CLI at purchase time; self-hosters build their own from the template. The binary is named after the brain, with the brain's endpoint and API key already baked in. Writes are accepted because the binary is pre-authenticated to the brain it was built for.

Under the hood, all brainfoundry CLIs share the same source. The binary is renamed and the default endpoint is baked at provision time.

You do not CLI into someone else's brain. `alice` talks only to alice's brain. Federation — brain-to-brain context sharing — happens server-to-server between nodes, not through a CLI. The CLI drives its own brain; brains federate with their peers.

## Visitor path — `nous`

### Install

```
pip install nous
```

That is the whole install. The package is a thin client with the public demo brain's endpoint already configured. No initialization step, no config file to edit.

### Chat

```
nous chat "what is brainfoundry"
nous chat "how is sovereignty enforced"
nous chat "what does a brain look like inside"
```

The demo brain runs a retrieval pass over a curated corpus about brainfoundry itself, and the model composes a grounded response. Output streams to stdout. A visitor can explore the product conversationally before committing to a self-host or a purchase.

### Writes are gated

Mutating verbs exist in the CLI — `upload`, `forget-doc`, anything that changes state — but the public demo brain rejects them for non-operators. The demo brain is public-read by design. If a visitor runs `nous upload`, the brain returns a structured error pointing at the provisioner with the message: writes require owning a brain.

This is a deliberate architectural property, not a UX limitation. Nobody has authorization to write to someone else's brain, including the demo brain. Writes arrive on a brain only through a CLI that was built for that brain.

## Owner path — branded CLI

When you buy a brain or self-host one, you end up with a CLI that is yours. Using `alice` as a generic owner example:

```
alice chat "what did I write about X last month"
alice upload ~/notes.md
alice stats
alice forget-doc notes.md
```

On a brain you own, the full verb set is available. `chat` runs retrieval over your memory and returns a grounded answer. `upload` chunks a file, embeds each chunk, and writes it into the vector store; the document is retrievable on the next chat turn. `stats` reports documents and chunks by layer. `forget-doc` removes a named document. Every mutation still passes PROPOSE → CONFIRM through the governance kernel — the branded CLI does not skip governance, it just carries the credentials to satisfy it.

If the brain's owner is Bob, the CLI is `bob`. Each owner's CLI is the same tool, renamed and pre-pointed.

## Getting your own brain — two paths

### Path 1: self-host

If you are comfortable administering a Linux server, clone the public template and deploy it.

```
git clone https://github.com/hbar-systems/brainfoundry-nous.git my-brain
cd my-brain
cp .env.example .env
```

Fill in the required fields in `.env` — see `docs/DEPLOYMENT.md` for the full list and `docs/SELF_HOSTING_GUIDE.md` for the complete walkthrough. Briefly: a unique `BRAIN_ID`, a display name, your owner name, a set of secrets generated with `openssl rand -hex 32`, and an ED25519 keypair generated with `python scripts/generate_keypair.py`.

Then:

```
docker compose up -d --build
```

The services start, the kernel initializes, and the API is available on its configured port. Put a reverse proxy in front with TLS, add a DNS record pointing at your server, and your brain has a public endpoint.

Self-hosters pick a CLI name for their brain and build their own branded binary from the template's CLI package. The build takes a binary name (e.g. `alice`) and a default endpoint (e.g. `https://brain.yourdomain.com`) and produces a CLI pre-pointed at your server.

The full reference is `docs/SELF_HOSTING_GUIDE.md`. It covers configuration, persona, ingestion, models, federation, production hardening, and troubleshooting.

### Path 2: buy a spawn from the provisioner

If you do not want to administer a server, the provisioner spins up a brain for you. You pay, the provisioner creates a fresh box, installs the runtime, issues keys, and emits your branded CLI.

After the provisioning flow completes, you get back a one-line install:

```
pip install alice-cli
```

(For a different owner the package name changes — `pip install bob-cli`, and so on.) The installed binary is `alice` (or `bob`, or whatever your brain is named), with the endpoint to your brain and the API key already baked in. Run `alice chat "hello"` on your laptop and the CLI is pointing at your brain. The provisioner steps out of the loop. Upgrades, changes, and deletions are your decision from that moment on.

## First things to do with a fresh brain

1. **Write the persona.** Edit `api/brain_persona.md` on the server and describe who you are — role, current work, reasoning style. The brain injects this into every chat. A thin persona produces generic answers; a rich one produces specific ones.

2. **Ingest something.** Point ingestion at a folder of your notes:
   ```
   python scripts/ingest_folder.py /path/to/your/notes
   ```
   Anything the script understands — text, markdown, PDFs — becomes retrievable immediately.

3. **Organize into layers if you want priority.** If you put files in folders named `identity`, `thinking`, `projects`, `writing` before ingesting, the brain gives those chunks priority in retrieval. Other folders go into the general corpus.

4. **Pick a model.** By default, the brain uses a local model via Ollama, which costs nothing per request. Adding an API key for a cloud provider in `.env` unlocks that provider in the model selector — your key, your billing, your choice per conversation.

5. **Ask it something real.** "What am I working on" is a good first question. If the answer is specific and grounded in your persona and ingested documents, the brain is working. If it is generic, the persona or the corpus needs more substance.

## Updating, pinning, or forking

Your brain is a git clone of the template. You choose when to pull and what to pull.

Track the main branch:

```
cd ~/brain
git pull origin main
docker compose up -d --build api ui
```

Pin to a specific commit for reproducibility:

```
git fetch
git checkout <commit-sha>
docker compose up -d --build api ui
```

Fork and run your own changes — also fine. The only contract that must stay compatible across forks is the federation protocol (`GET /identity` and `POST /v1/federation/assertion`), so other brains can still verify you.

## License

The brainfoundry-nous repository is AGPL-3.0. Run it, modify it, self-host it freely. If you run a modified version as a service to others, you must release your modifications under the same license.

## Summary

- `pip install nous` — public CLI with the demo brain's endpoint baked in. Visitors chat with the demo brain read-only.
- Branded per-brain CLIs (`alice`, `bob`, ...) — generated by the provisioner at buy-time, or built locally by self-hosters. Pre-pointed at the owner's brain with writes enabled.
- You do not CLI into someone else's brain. Each CLI talks only to the brain it was built for.
- Self-host or buy a spawn to get your own brain.
- Your brain, your data, your keys, your code.
