# Privacy and memory

*Created 2026-10-16. Applies to brainfoundry-nous with the privacy gate (2026-10-14) and the private vault (2026-10-15). Updated 2026-10-16: the brain-app gap is closed (the app lane).*

This document explains who can read what your brain remembers. It says what the brain protects, how it decides, and what it does not protect. The engineering version is section 4a of `THREAT_MODEL.md`; this one is for the person who owns the brain.

## Two kinds of memory

Everything your brain remembers is stored in small pieces called chunks. A chunk is a few paragraphs of a document, kept with a note of where it came from.

Every chunk carries a privacy level. There are two.

| Level | Who may read it |
|---|---|
| `open` | Any model the brain uses, on your server or at a provider. This is the default. |
| `local-only` | Only a model running on hardware you control, answering you in the console. |

A chunk with no level is open. Brains made before this feature keep working, and all their memory counts as open.

You choose the level in three places:

- **Before an upload.** On the Knowledge tab, the Privacy chips (open / local-only) sit next to "Memory layer". Pick one, then upload.
- **After an upload.** In Knowledge, Browse, each document has a chip. Click it to flip that document between open and local-only.
- **From a brain-app or a script.** The memory write call takes a `privacy` field. An app passes `privacy: "local-only"` in `memory.write`.

Some rules keep a level from slipping by accident. Uploading a local-only document again, without choosing, keeps it local-only. Appending text that is already stored as local-only keeps it local-only. Anything stored from a session that read local-only memory is stored local-only.

## Closed models and local models

The brain talks to two kinds of model.

A **hosted model** runs at a company: Anthropic, OpenAI, Google Gemini, xAI, Groq, OpenRouter, Together, Mistral. When the brain uses one, it sends the prompt over the internet to that company. The brain calls these models **closed**, because you cannot see where the text goes after it leaves.

A **local model** runs in Ollama on your own server, or on a machine of yours that the brain reaches over your private network (a "spoke"). The text never leaves hardware you control.

### How the brain tells them apart

The brain does not ask the model what it is. It looks at the address the request will be sent to.

A model counts as local only when all of these are true:

1. The brain routes it to Ollama, not to a provider's API.
2. Its name does not end in `:cloud` or `-cloud`. Ollama forwards those models to ollama.com, so they are hosted.
3. Every Ollama address the brain could send it to is on your own network space.

"Your own network space" means one of these:

- a plain name with no dot, like `ollama` (the brain's own container) or a machine name on your home network;
- `localhost`, or a private address such as `192.168.x.x` or `10.x.x.x`;
- a Tailscale address (`100.64.0.0/10`) or a name ending in `.ts.net`, `.local`, `.internal`, `.lan` or `.home.arpa`;
- a host you list yourself in `PRIVACY_LOCAL_HOSTS`.

Anything else is closed. When the brain cannot tell, it treats the model as closed. This is called failing closed: doubt never opens a door.

### The limit of judging by address

An address says where a request goes. It does not say who owns the machine there.

If you point the brain's Ollama at a private address on a network you do not control, the brain will call that model local. A plain name with no dot is trusted the same way. The brain trusts you to point it only at your own machines.

### Your own list of local readers

Locality says a model *can* be trusted with local-only memory. Your list says you *do* trust it.

By default there is no list, and every local model may read local-only memory. You can narrow it to named models in Knowledge, Vault, with the chips under "Local models that may read local-only memory". The same setting can be made on the server with `BRAIN_LOCAL_READERS` (a comma-separated list, or `none` for no model at all). A local model that is not on your list is treated exactly like a hosted one.

The list matches names, not the model files themselves. If a different model is pulled under an allowed name, it is allowed too.

## What each surface sees

A surface is a place where someone or something talks to your brain. Local-only memory reaches a model only when two things are true: the model is a local reader on your list, and the answer comes back to you in the console.

| Surface | Open memory | Local-only memory | Why |
|---|---|---|---|
| Console chat, local model on your list | yes | yes | The text stays on your hardware and the answer returns to you. |
| Console chat, hosted model | yes | no | The prompt goes to a company's servers. |
| Brain-apps (`llm.complete`) | yes, in the layers the app asks for | no, even on a local model | The answer goes into the app's own code. |
| Telegram (the brain's bot) | yes | no, even on a local model | Every message and reply passes through Telegram's servers. |
| Public chat | only the `public` layer | no | The reader is a stranger. |
| Federation (other brains asking) | only the `public` layer | no | The reader is another brain, not you. |
| The background autonomy loop | yes | no | Nobody is reading the answer as it happens. |

The filter runs twice. The database query leaves local-only chunks out, and the brain checks the result again before it builds a prompt. A chunk with a level the brain does not recognise counts as local-only.

Every reply carries a small note saying whether the model was a local reader and whether it used local-only memory. In the console this shows as the chat header.

## The session mark

Here is the problem the mark solves.

You ask a local model about your therapy notes, which you keep local-only. It answers, and it quotes a sentence from them. That quote is now part of the conversation history.

Then you switch the same conversation to a hosted model. Each turn sends the conversation history along with your new message. Without a mark, the quote would travel to the provider, even though the notes themselves never did.

So the brain marks the session. The first time any turn puts a local-only chunk in front of a model, the session is marked local-only, and the mark stays.

In a marked session:

- A hosted model may not continue it. Neither may a local model off your list, nor a brain-app.
- "Save to memory" summarises it only with a model that may read it (the local default). The summary is stored local-only.
- The Store button's classifier refuses a hosted model. Anything you store from the session lands local-only.

### What you see

The session list shows a "local-only" tag on the session. The chat header shows "local-only · GREEN tools only".

If you pick a hosted model and send a message, nothing is sent. Your message goes back into the box where you type it, and a banner says:

> This session carries local-only memory (a local model quoted it here), so a hosted model may not continue it. Start a fresh session to use this model, or pick a local model to continue.

The banner offers to start a fresh session.

### The limits of the mark

- It covers one session. If you copy text out of a marked session by hand and paste it somewhere else, it is ordinary text again.
- Sessions from before 2026-10-15 carry no mark, even if a local model quoted local-only memory in them. Start fresh sessions for hosted models, or delete those old ones.
- The console always says which session a message belongs to. A program that calls the API directly and leaves the session out is not caught.

## Tools during a private turn

In chat, a model can use tools: search your memory, search the web, fetch a page, ask another brain, read mail or a calendar.

Once a turn holds local-only memory, only GREEN tools may run for the rest of that turn. GREEN tools read your own memory and your own task list, and nothing leaves the server.

Web search, page fetch, asking another brain, mail, Drive, calendar and MCP tool packs are refused. The reason is simple: a tool call carries words the model chose, and those words leave the box. A model that has just read your notes could put a piece of them into a search query.

The "your mind" fact extraction, which pulls facts about you out of a conversation, is skipped for that turn if its model is hosted.

## The private vault

Memory levels control which model reads a chunk. They do not stop a program on the server from reading the original file. The vault does.

### What it is

The vault is a folder on the server that only you can read. By default it is `/home/<you>/vault`. Its permissions are set so that only your own Unix user can open it.

The Claude and Codex seats run as a separate user called `hands`. The CC bridge runs as a user called `cc`. Neither can list the vault or open a file in it.

The brain reads the vault through a read-only connection into its own container. It turns the text files into memory and marks every one local-only. Those documents are named `vault/<path>`, and the brain refuses to make them open while the file is in the vault.

The brain never copies a vault file anywhere: not to the desk, not to the world checkout, not into an export. The only thing it writes about the vault, outside the database, is a list of file names, sizes and fingerprints, used to notice changes.

### What goes in

Text files are read: `.md`, `.txt`, `.org`, `.json`, `.csv`, `.yaml`, `.html`, code files and similar. Each file may be up to 5 MB.

Some files are left out:

- PDFs, images, audio and other non-text files are not read;
- hidden files and folders (names starting with a dot) are skipped;
- links to files elsewhere are never followed.

### How to set it up

Do this once, on the server, logged in as yourself. Not as `hands` or `cc`, and not by asking an agent to do it.

1. Update the brain to a version that knows about the vault.
2. In the brain's folder, run `scripts/vault-setup.sh`. It creates the folder, connects it to the brain read-only, and checks that `hands` and `cc` cannot read it. It asks for your password for those checks. It refuses to continue if `hands` or `cc` belongs to the `docker` group, because that group can read any file through Docker.
3. Run `docker compose up -d api` so the brain picks up the folder.
4. Put files in the vault, then open Knowledge, Vault, and press **Scan now**.
5. To check the wall again at any time, run `scripts/vault-setup.sh --check`.

After that, the brain scans the vault every 10 minutes and picks up new and changed files. Removing a file from the vault does not remove its memory. Press **Scan and forget removed files** for that.

### Who reads it

- **Can read it:** you, a local model on your list answering you in the console, the server's root user, any member of the `docker` group, and anyone who holds the brain's API key (see below).
- **Cannot read it:** hosted models, the Claude seat, the Codex seat, the CC bridge, brain-apps through `llm.complete`, Telegram, public visitors, other brains.

### The read audit

Every turn that put local-only chunks in front of a model writes one line to the brain's audit. The line records the time, the model, the address it ran on, the session, where the turn came from, the document names and how many chunks. It never records the content.

You can see these lines in three places:

- Knowledge, Vault, under "Recent reads";
- the Trace tab;
- the API route `/tools/audit`.

## What is NOT protected

These are honest gaps. Each one is something the privacy gate does not do.

**Files outside the vault.** A document you marked local-only may also exist as a file in your world checkout, in the desk folders `in/` and `out/`, or anywhere else `hands` can read. The Claude and Codex seats can read that file, whatever its memory level, and what they read goes to Anthropic or OpenAI. The Codex seat can read anywhere `hands` can, without asking. Put private files in the vault, not on the desk.

**No encryption at rest.** The brain does not encrypt your memory. A local-only chunk is plain text in the database, like any other. The gate decides which model reads it; it does not decide who can read the database. Root on the server, the `docker` group, and anyone with a copy of the disk can read everything. Whether your host encrypts the disk itself is a question for your host. (Integration passwords, such as a mail app password or a Telegram bot token, are encrypted in the settings file. That is a separate protection.)

**Backups contain everything.** `scripts/backup_brain.sh` copies the whole database: open memory, local-only memory, vault documents and chat history. Exports are different: they leave vault documents out unless you ask for them (`INCLUDE_VAULT=1 scripts/export.sh`). Keep backups where you would keep the originals.

**The API key holder.** Whoever holds the brain's API key can ask the API for local-only chunks and for chat history. Keep the key where `hands` and `cc` cannot read it: the brain's `.env` and the bridge's own settings file. If a Claude Code run could read the key, it could call the API itself.

**Brain-apps are fenced off from the console (closed 2026-10-16).** Until 2026-10-16 an installed app ran in the console's own web address, and the console passes requests to the brain with your API key added. So an app's code could reach what the key reaches, local-only memory and chat history included, and could even read the key itself. That gap is closed. An app now runs in a sealed frame with no web address of its own: it cannot read the console page, and the console refuses every request that comes from such a frame. The brain's other doors on the console (the permit route, the CLI-info route, the CC bridge and the terminal) refuse it too. An app reaches the brain only by asking the console page, which checks each request against what you approved when you installed the app. None of those requests returns local-only memory. The app's own files still load, and its saved settings are kept for it by the console, one store per app. What this does not cover: an app that ships its own server code (`entries.api` in its manifest) runs that code inside the brain's API, with the API's authority, so read that code before you install such an app. The details are in section 4b of `THREAT_MODEL.md`.

**Embeddings at ingest.** To make text searchable, the brain turns every chunk into a list of numbers, called an embedding. This happens for every chunk, whatever its level, vault files included. It runs on the server, or on an embedding spoke if you set one. If that spoke is not your own machine, local-only text reaches it at ingest.

**The allowlist matches names.** Your list of local readers names models. A different model pulled under an allowed name is allowed.

**The address rule trusts you.** A private address you do not control, or a plain name that points somewhere else, counts as local. Point the brain only at your own machines.
