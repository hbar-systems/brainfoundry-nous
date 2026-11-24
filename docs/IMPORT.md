# Import: a year of ChatGPT, Claude or any other AI into the brain

Created: 2026-10-13.
Tool: `scripts/import_chats.py`. Tests: `tests/test_import_chats.py` (synthetic fixtures only).

One rule: the person brings the material, the brain never goes looking for it.
Nothing in this path writes memory directly; every document goes through the same permit, propose, approve gate as a Knowledge-tab upload.

## 1. Get the export (the person's own button)

- ChatGPT: chatgpt.com, Settings, Data controls, Export data. The mailed zip holds `conversations.json` (a top-level array; each conversation is a `mapping` tree of messages), sometimes sharded as `conversations-000.json`, `-001`, ...
- Claude: claude.ai, Settings, Privacy, Export data. The zip holds `conversations.json` (an array; each has `name`, `created_at`, `chat_messages` with `sender` and `text`), `projects.json` and `users.json`.

The zip comes to the brain through the console's Files upload, not by email.

### The Knowledge page card (2026-10-25)

The short way: the card "Import your ChatGPT or Claude history" at the top of the Knowledge page (/upload) takes the zip and calls `POST /documents/import-chats` (`api/chat_import.py`). The api runs steps 2 to 4 with `--newest 50` in a scratch folder under its runtime volume (removed afterwards), proposing each conversation through the same permit and Path A as a Knowledge upload. It answers with the counts (conversations, selected, proposed, flagged, sources, manifest id); the proposals wait in Pending on the same page, one approval each or Approve all. Nothing is remembered before that. Projects are left out, as in `select`.

## 2. Prep: one document per conversation

```
python3 scripts/import_chats.py prep <export.zip | unzipped dir | conversations.json> prepared_docs/import_2026-10-13
```

- Reads the zip directly (no unzip needed), every `conversations*.json` shard, and `projects.json`. ChatGPT and Claude are told apart per conversation (`mapping` vs `chat_messages`).
- Writes `docs/<source>_<date>_<title-slug>_<id8>.md`: title, start date, then `## Me, <time>` and `## Assistant (ChatGPT|Claude), <time>` turns. That file name becomes the document name in memory, so the brain can say "from your ChatGPT, March 2024".
- ChatGPT: main branch only (walked from `current_node` up through parents; without it, the latest child at every fork). Regenerated answers, system and tool messages, hidden context and tool calls are dropped; images become `[image]`.
- Claude: text or text blocks per message; attachments with extracted text are kept inline as `[attachment: name]`. Each project becomes one `claude-project_...md` document (description, standing instructions, project docs); projects are left out of selections unless asked for (`--with-projects`), since they are `ME.md` and `areas/` candidates first.
- Nothing is cut. The old 200,000-character cap on the whole export is gone; a long conversation is one long document and the API chunks it.
- `index.tsv`: id, source, kind, date, updated, title, turns, chars, file, sha256; newest first.

## 3. Selection: what goes in, what stays outside

```
python3 scripts/import_chats.py list   prepared_docs/import_2026-10-13 [filters]
python3 scripts/import_chats.py select prepared_docs/import_2026-10-13 [filters]
```

Filters: `--since YYYY-MM-DD`, `--until YYYY-MM-DD` (inclusive), `--newest N`, `--max-chars N`, `--include FILE` (only these), `--exclude FILE` (strike these), `--with-projects`.
An include or exclude file has one entry per line: a conversation id, a document file name, or a prefix of either; `#` starts a comment.
The person strikes what stays outside (health, other people, a job) in an exclude file.

`select` writes `manifest.tsv` with a header line `# manifest_id: <16 hex>`.
The id is the hash over every selected row's conversation id and document hash, so it names exactly this selection of exactly these texts.
Unselected documents stay as files in the prep folder (move them into `library/` if the person wants them kept); they are not indexed.

A year of chats swamps a fresh brain (a year of daily use can be about 8.5M tokens).
Start with `--newest 50` or the person's own include list; more can be selected later into a second manifest.

## 4. Propose: through the gate

```
BRAIN_API_KEY=... python3 scripts/import_chats.py propose prepared_docs/import_2026-10-13 --api http://localhost:8010 [--layer NAME]
```

- Asks the brain for an upload permit (`POST /documents/upload/permit`; NodeOS issues a loop permit that lives 300 s), then posts each manifest document to `POST /documents/upload` with that `permit_id`.
- The API extracts the text, runs the injection scan, records a NodeOS memory proposal and returns `202 PENDING` with a `proposal_id`. Nothing is in memory yet.
- One permit covers the whole run while it lives; the client takes a fresh one every 240 s or when the brain answers that the permit expired. Each proposal row records the permit it was made under.
- `proposals.tsv` is written after every document, so an interrupted run resumes where it stopped and never proposes a document twice.
- The pending proposals show in the console's Knowledge tab like any upload; the person can approve or reject there one by one instead of step 5.

## 5. Approve: one yes for a named manifest

```
BRAIN_API_KEY=... python3 scripts/import_chats.py approve prepared_docs/import_2026-10-13 --api http://localhost:8010 --yes <manifest_id>
```

This is the batch approval (gap E). It is not a new authority path; it uses the brain's existing server-side approve, `POST /documents/approve-all` with an explicit `proposal_ids` list, which decides APPROVE in NodeOS and then runs the same Path B ingest as the Knowledge tab, one audit record per decision.
What the client adds is the binding of that one yes to what the person reviewed:

- `--yes` must equal the manifest id recomputed now from `manifest.tsv`; any other value approves nothing.
- Every document must still hash to the sha256 recorded at select time; one changed byte and nothing is approved.
- Every row must already be proposed; only those proposal ids are sent, never "all pending".
- Documents the injection scan flagged (risk other than none or low) are left PENDING and listed; the person reads them in the Knowledge tab, or reruns with `--include-flagged`.
- `approval.json` records the manifest id, UTC time, count approved, flagged left pending and any failures. That line is the "Yes given (date, how)" for `library/MANIFEST.md`.

Who may press it: whoever holds the brain's API key is the operator. For a person's own brain that is the person; an agent or technologist running the import for them proposes, shows them `manifest.tsv` and the id, and runs approve only with their dated yes.

Limits: `approve-all` lists at most 1000 pending proposals, so keep manifests under 1000 documents (or approve the first manifest before proposing the next). If a batch is already running on the brain, the ids are queued behind it.

## 6. After

- Add a row to `library/MANIFEST.md` (source `chatgpt` or `claude`, date of the export, manifest id, the yes from `approval.json`).
- Exit is unchanged: `scripts/export.sh` takes everything back out (docs/EXPORT.md).
- `scripts/import_chatgpt.sh <zip> [label] [filters]` runs prep, select and propose in one go and prints the approve line; it never approves. `scripts/prep_chatgpt_export.py` is kept as a shim onto `prep`.
- Not yet done: linking each document to a `source/<export>` entity (the old script's step 4, which needs the in-container SemanticDB); the file-name prefix carries source and date meanwhile.

## 7. Inbox and sorter (loose folders): built 2026-10-17

Tool: `scripts/sort_inbox.py`. Tests: `tests/test_sort_inbox.py` (made-up files only).
No laptop scan; the person drops everything they have into one inbox folder per brain (`library/inbox/` in their world, filled by the console's Files upload or a synced folder). Nothing outside it is read.

```
python3 scripts/sort_inbox.py sort library/inbox prepared_docs/inbox_2026-10-17 [--llm] [--owner NAME] [--brain-name NAME]
```

- Walks the inbox: names, sizes, extensions, and the first lines of text, md, docx and pdf (pdf text only if `pypdf` is installed, else its title). Images, audio and video by name and type only. Nothing is run, links are listed and not followed, `.DS_Store` and `__MACOSX` are ignored. The inbox itself is never changed; the sorter copies.
- ChatGPT and Claude exports (a zip holding `conversations*.json`, or an unzipped export folder) go to `import_chats.py prep` into `<out>/chats/<name>/`; the person picks from them with `select` as in step 3 (a year of chats is too much for one yes).
- Exact duplicates (same sha256) are listed and skipped.
- Every other file gets one area and a short reason: `identity`, `projects`, `writing`, `thinking` (the folders retrieval pins, `RAG_TIER1..2C` in `api/main.py`), `library` (kept as a file, not remembered: images, audio, data, anything no rule placed), or `outside` (keys, passwords, bank, tax, health, IDs: not copied, never offered).
- Rules decide: names first (`cv`, `roadmap`, `essay`, `journal`, a dated name ...), then headings (`# About me`, `## Milestones` ...). It works with no model at all. With `--llm`, only text files no rule placed are sent (name and first 1500 characters) to the brain's own model through `POST /chat/completions` under a NodeOS loop permit; if the model fails, the rule result stands. That model may be a cloud provider, so `--llm` is the person's choice.

Writes into `<out>`:
- `identity/ projects/ writing/ thinking/ library/`: the filed copies.
- `sorted.tsv`: every file: file, source, sha256, area, reason, size, kind.
- `manifest.tsv`: the rows to remember (the four pinned areas), with `# manifest_id:` in the same form as step 3. Its `name` column (`identity/cv.md`) is the document name in memory, so retrieval pins it.
- `summary.txt`: e.g. `42 files: 5 identity, 8 projects, 12 writing, 9 thinking, 4 library, 1 outside; 3 duplicates skipped; 1 chat export`, then the manifest id and the next commands.
- `persona_draft.md` (below).

The person corrects the sort by editing the area column of `sorted.tsv`, then:

```
python3 scripts/sort_inbox.py manifest prepared_docs/inbox_2026-10-17
```

which moves the filed copies and writes `manifest.tsv` again under a new id.

Remember: steps 4 and 5, unchanged. Same permit, one proposal per document, same hash check, one yes for the named manifest id:

```
BRAIN_API_KEY=... python3 scripts/import_chats.py propose prepared_docs/inbox_2026-10-17 --api http://localhost:8010
BRAIN_API_KEY=... python3 scripts/import_chats.py approve prepared_docs/inbox_2026-10-17 --api http://localhost:8010 --yes <manifest_id>
```

(`propose` now sends the manifest's `name` column when it has one, and pdf/docx with their own content type so the api extracts them; chat manifests are unchanged.)

### Persona draft

`sort` writes `persona_draft.md`; `persona <out>` writes it again after the sort has been corrected. It has the shape of `api/brain_persona.template.md` (banner and `[CONFIGURE]` block stripped as `api/persona_tools.py` does), with an "About <owner>" block before `Identity:`: lines from the identity files, project titles, writing titles and two plain style notes, each line naming its source file. It opens with a `# DRAFT` banner. The owner name comes from `--owner` or a `Name:` line in an identity file; otherwise `[OWNER_NAME]` stays for the person to fill.

The person reads it, edits it if they want, then:

```
BRAIN_API_KEY=... python3 scripts/sort_inbox.py persona-approve prepared_docs/inbox_2026-10-17 --api http://localhost:8010 --yes <draft_id>
```

`--yes` must equal the hash of the draft as it is on disk now (an edit changes it; a wrong id prints the right one and writes nothing). The banner is stripped and the text goes through `PUT /persona`, the Persona page's own save; `persona_approval.json` records the id, time and any placeholders left.

Not built yet: the console card review (one card per folder) and picking folders on the person's own spoke; both use these files as they are.

## From your laptop: folder by folder (2026-11-03)

The on-ramp for everything that is not a chat export. Pull by the person: the helper runs on their own computer, at their command, and sends only what they say yes to. The brain never holds a door into the laptop (no inbound shell, no agent left running there).

Helper: `scripts/import/brain_import.py` (one file, Python 3.8+ standard library only, Mac, Windows, Linux). Brain side: `api/laptop_import.py` and four routes in `api/main.py`. Tests: `tests/test_laptop_import.py` (rules, secret skips, token store, and an end to end against the api on 127.0.0.1 over a temp folder tree).

### The steps

1. In the console, the owner mints a one-time token: `POST /documents/import-laptop/token` (owner key). It lives 2 hours, carries a cap of 2000 files and 2 GB, is stored only as its sha256, and closes every earlier token.
2. The person pastes one command on their computer (Mac or Linux; on Windows use `curl.exe` and `python`):
   ```
   curl -fsSLo brain_import.py https://<brain>/api/bf/documents/import-laptop/helper.py && python3 brain_import.py --brain https://<brain>/api/bf --token imp_...
   ```
   The helper comes from the person's own brain (`GET /documents/import-laptop/helper.py`); it can be read before it runs. `--dry-run` only lists.
3. It lists Documents, Desktop, Downloads, Music, Pictures, Movies/Videos, and project folders (a top-level folder named Projects, Code, dev, src, repos, work, ... or one holding a `.git`), each with file count, size, what is offerable by type, and what is never sent. Per folder: `y` (documents and text: txt, md, pdf, docx, csv, code, ...), `n`, or a list of types (`pdf,md,jpg`; images only when named, they go through OCR).
4. One confirmation, then each chosen file goes to `POST /documents/import-laptop/file` with the token, with a progress line per file. The brain checks and charges the token, extracts the text (the same extractors as a Knowledge upload), and proposes it through an upload permit as `laptop/<Folder>/<path>`. It answers PENDING with a proposal id.
5. `POST /documents/import-laptop/finish` closes the token. A receipt `brain-import-receipt-<time>.json` (sent with proposal ids, refused with reasons) is written where the helper ran.
6. The files wait in Pending on the Knowledge page (/upload): one approval each, or Approve all. Nothing is remembered before that.

### Never sent, by rule (in the helper, whatever the answer)

- Hidden files and folders: `.ssh`, `.gnupg`, `.aws`, `.config`, `.env`, `.netrc`, `.git`, ... (the survey's one exception, 2026-11-23: the session files of `~/.codex/sessions` and `~/.claude/projects`, see "Codex and Claude Code history" below)
- Key, password and vault files: `id_rsa*`, `id_ed25519*`, `*.pem`, `*.key`, `*.p12`, `*.pfx`, `*.kdbx`, keychains, 1Password/Bitwarden/KeePass folders and exports, `*.gpg`, `*.asc`, `*.ovpn`, and any name holding `password`, `secret`, `credential` or `token`.
- System and app folders: `Library`, `AppData`, `Program Files`, `node_modules`, `venv`, `build`, `dist`, photo libraries, app bundles.
- What the brain cannot use: video, archives, databases.
- Files over 25 MB (audio: over 200 MB).

Audio, MIDI and Ableton sets (`wav aif aiff mp3 flac m4a ogg mid midi als`, 2026-11-03) are not read into Knowledge: `y` on a folder named Music brings them with the documents there, elsewhere they go when named (`wav,mp3`).

The brain checks again on its side: a path with `..`, a root or a hidden part is refused (400), a type it cannot read is refused (415), a spent, replaced or expired token is refused (401), the run's caps answer 413. The token can only propose into Knowledge; it is not the owner key and the owner key does not work in its place.

### The Knowledge card (2026-11-03)

The Knowledge page (/upload) carries "Bring files from your computer". Start mints the token (`POST /documents/import-laptop/token` through the console, behind the login) and shows the one line to paste, for Mac (Terminal) or Windows (PowerShell), with a Copy button. The line works once, for two hours; New line mints another and closes the old one. While it runs, the card asks `GET /documents/import-laptop/status` (owner key; the newest run's counts and what arrived, never a token) every 4 seconds: documents are listed and appear under Pending for approval, music is listed with where it was kept. `ui/lib/LaptopImportCard.js`.

### Music: kept as files in ~/in, not remembered

An audio file goes to the same `POST /documents/import-laptop/file` with the same token. The api streams it to a temp file (200 MB cap per file, counted against the run's caps), then keeps it at `LAPTOP_AUDIO_DIR/<date of the run>/import/<laptop path>` (a name already there gets ` (2)`; nothing is overwritten), mode 644, owned like the folder, and appends a line to `audio.tsv` in that `import/` folder (`file bytes sha256 arrived`) for the music tools. It is never proposed to memory. The answer is `KEPT` with `where: in/<date>/import/...`.

`LAPTOP_AUDIO_DIR` is `/app/laptop_audio` in the container. `docker-compose.yml` mounts `LAPTOP_AUDIO_HOST_DIR` there; `scripts/member_env.py` sets it to `/home/<handle>-hands/in` for every new member, and `scripts/add-member.sh` makes that folder (owned by the hands) before the stack starts, so the music lands in the member's own `~/in/<date>/import/`, beside the console's attachments. Unset (a single brain), a docker volume `laptop_audio` keeps it and the card says "kept on your brain".

### The way in from the laptop (Caddy)

The console sits behind its login; the helper carries only the token. So the console site block opens exactly the four token-gated paths, straight to the api (the console's own `/api/bf` proxy would add the owner key), and keeps the login for everything else, `/token` and `/status` included. `scripts/add-member.sh` prints it in every new member's block. The snippet, for any console block (`<api port>` is the brain's api port):

```
    @import path /api/bf/documents/import-laptop/helper.py /api/bf/documents/import-laptop/check /api/bf/documents/import-laptop/file /api/bf/documents/import-laptop/finish /api/bf/documents/import-laptop/refused /api/bf/laptop/agent.sh /api/bf/laptop/agent.ps1
    handle @import {
        uri strip_prefix /api/bf
        reverse_proxy localhost:<api port>
    }
    @login not path /api/bf/documents/import-laptop/helper.py /api/bf/documents/import-laptop/check /api/bf/documents/import-laptop/file /api/bf/documents/import-laptop/finish /api/bf/documents/import-laptop/refused /api/bf/laptop/agent.sh /api/bf/laptop/agent.ps1
    basicauth @login {
```

(the last line replaces the block's `basicauth {`; the hash line under it stays). Checked on caddy 2 with a stand-in api: the four paths pass without the password and arrive without an owner key; `/token`, `/status`, `file/../token`, `%2e%2e` and the rest of the console answer 401.

Existing boxes (one line): back up `/etc/caddy/Caddyfile`, add the snippet to each console block, `caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile`, `sudo systemctl reload caddy`; for music into a member's `~/in`, add `LAPTOP_AUDIO_HOST_DIR=/home/<handle>-hands/in` to that member's .env, make the folder as the hands if missing, and rebuild the api. The central thread applies this on hbar's word.

### Not done yet

- Resume after a broken run (the receipt lists what went; a second run needs a new token and resends).
- Mac and Windows runs of the helper are untested here (Linux only).

## Moving in, two doors on the home (2026-11-16)

hbar 2026-11-16: "the main idea is for the user to switch over to the brain". A member moves in in one sitting from two cards on the console's quiet home (`ui/components/MoveInCards.js`, words in `ui/lib/moveInPlan.js`, en and ru by the console's lang key). Tests: `tests/test_move_in_survey.py`, `tests/test_move_in_plan.py`.

### Door 1: the whole computer (survey)

1. Home card "Bring your whole computer", Start. The console mints a survey token: `POST /documents/import-laptop/token` with body `{"survey": true}` (owner key). Caps of a survey run: 20,000 files; 20 GB on a brain's own box, 8 GB for a member on a shared box (`LAPTOP_AUDIO_HOST_DIR` set; half the 15 GB member disk quota), `LAPTOP_SURVEY_MAX_GB` overrides; never more than the free disk less a tenth of the disk. It lives 6 hours. Per file unchanged: 25 MB, audio 200 MB. A folder-by-folder token keeps 2,000 files, 2 GB, 2 hours.
2. The person pastes the one line on the computer (Mac Terminal or Windows PowerShell; the card shows it with Copy). It is the folder-by-folder line plus `--survey`.
3. The helper walks the whole home folder and the mounted cloud folders: iCloud Drive (`~/Library/Mobile Documents/com~apple~CloudDocs`), `~/Library/CloudStorage/*` (Google Drive, Dropbox, OneDrive, Box on current macOS), `~/Google Drive`, `~/Dropbox`, `~/OneDrive*`, `~/iCloudDrive` (Windows) and `<letter>:/My Drive` (Google Drive for desktop on Windows). Desktop, Documents, Downloads and Pictures are inside the home walk. The never-send rules are those of the folder-by-folder run, plus mail stores (`Mail`, `Thunderbird`, `*.pst *.ost *.mbox *.emlx *.olm`) and browser profiles (`Chrome`, `Firefox`, `Mozilla`, `Safari`, `User Data`, ...). Files never sent are only counted per folder, never named.
4. It sends an INVENTORY only, gzip JSON to `POST /documents/import-laptop/check` under the token: `files: [[path, size, modified], ...]` (at most 300,000 rows, 64 MB decompressed), `skipped: {"<folder>: <why>": n}`, `roots`. No content. The api checks every path (`clean_relpath`), drops types it does not take, and plans (`api/laptop_survey.py`): files grouped by area (first folder; a cloud folder keeps its name in front, `Google Drive/Work`; an area with over 400 knowledge files splits one folder deeper), each group proposed as `knowledge` (documents and text into Knowledge), `files` (music and pictures kept as files in `in/<date>/import/`, listed in `audio.tsv` / `media.tsv`), or `leave` with why: code (over 150 files, mostly code: it has its own git), downloads not touched for two years, screenshots on the Desktop or in Downloads, over 2,000 pictures in one group.
5. The home card shows the plan (`GET /documents/import-laptop/status` carries `survey`: groups without their path lists). One tick per group; "Bring all proposed" or "Bring the chosen" with the count and size; a choice over the run's caps is refused with the numbers. The yes is `POST /documents/import-laptop/plan` `{"take": [ids] | "proposed"}` (owner key, behind the console login).
6. The helper, still running, polls `GET /documents/import-laptop/check` every 3 s; once chosen, the answer carries `take.paths` (`[path, kind]`). It sends only names that are in its own inventory (anything else is counted and ignored), through the existing `POST /documents/import-laptop/file` (pictures with `keep=file`), then `finish` closes the token. Documents wait under Pending for the one yes (the card's Remember button); music and pictures are kept, never remembered.

Pull only: the helper runs once at the person's command, nothing is left running on their computer, the brain holds no door into it and cannot name a file the helper did not list. No new way in from outside: the inventory and the choice travel on `/documents/import-laptop/check`, one of the four token paths Caddy already opens; `/plan` and `/status` stay behind the console login.

Phone: the card says to put photos and files in iCloud Drive or Google Drive; the computer's run sees them there.

### Door 1 without a line: over the spoke (SWITCH-1, 2026-11-16)

When the brain has a spoke (`docs/spoke.md`) and the computer joined it, the home's **Connect this computer** card starts the same survey without a pasted line: the console mints the survey token, the bridge hands it to the laptop's `door.sh move-in` on stdin (organise mode), and the laptop runs this same `brain_import.py --survey` against `<console>/api/bf`, detached. The plan, the yes and the pull below are unchanged. The helper takes the token from `BRAIN_IMPORT_TOKEN` when `--token` is absent, so it is never on a command line. The pasted line stays as the fallback.

### Door 2: chats from every AI, then Continue here

- The home card "Bring your chats with ChatGPT, Claude and other AIs" carries one chip per AI (`ui/lib/aiExports.js`) with that AI's export steps and link, takes the export file as it came (zip, json, html, csv) or a pasted conversation (the `text` field of `POST /documents/import-chats`), and says that signing in with Claude or ChatGPT (the seat) does not bring old chats; the export does. The Knowledge page's import card lists every AI the same way.
- Continue here (`api/chat_continue.py`): whenever a conversation document is proposed (any door: home, Knowledge page, `import_chats.py propose`), `_propose_document_text` keeps its starting point in `<runtime>/chat_continue/<sha256(name)[:24]>.json` (mode 600): title, AI, dates, turns, an extractive summary (first ask, last ask; no model call) and the last 6 turns verbatim (4,000 characters each). `GET /documents/chats` lists them with `state` in (approved) or waiting; conversations approved before this existed are listed from memory and rebuilt from their chunks on first use. `GET /documents/chats/continue?name=&lang=` gives the first message of a new thread: the old turns quoted (`> `) and framed as the person's old conversation, not instructions.
- The home lists "Your chats from ChatGPT and Claude" (the AIs found) with Continue here on each; the Knowledge page's document rows carry the same button for conversation documents. The button opens `/?continue=<name>`: the console opens a new thread and sends that first message. From another site, or when the import's injection scan flagged the conversation, it only fills the composer and waits for the person's send.

Not done yet: resume after a broken survey run (a new line resends); the survey walk on a real Mac and Windows (tested on Linux with made-up cloud folders); a group chosen while the helper is gone waits until the token expires.

## Pace: moving in at what a brain can read (IMPORT-PACE-1, 2026-11-24)

hbar, after two days of one member's sitting: "did we consider limits so we dont import from computer more than what brain can handle? notice how long the onboarding takes." That sitting: 1,865 files chosen (7.5 GB listed), 1,825 arrived, 40 refused; the brain's health check silent for 15 s during the run; the home showing three counts (card "479 wait, 21 kept", button "Remember all 1000", footer "200 wait"); the sitting stopped and went on the next day. The start (one pasted line, the list first, the choice on the home) stays as it is.

### Measured (synthetic files, 2026-11-24)

2 cores of a Neoverse-N1 (the core of the Hetzner CAX boxes), bge-large-en-v1.5 fp32 through ONNX Runtime with 2 threads (a stand-in for the container's torch; the container itself was not measured, docker is not reachable from the build box), batch 32, 512 tokens, CHUNKER=words. Scripts and raw numbers: `/home/hands/out/2026-11-24/import-pace-1/measure/` (rates.py, latency.py, rates.json, latency.json).

| file | words | chunks | read (extract + chunk + embed) |
|---|---|---|---|
| note | 403 | 1 | 12.5 s (10 notes, 12.46 to 12.86) |
| slide deck PDF, 25 slides | 1,550 | 4 | 63.8 s (3 decks, 63.3 to 64.3) |
| book PDF, 300 pages | 126,000 | 281 | measuring at commit time (expected about 75 min at 15.9 s a chunk) |

Embedding is nearly all of it: extracting the 300-page PDF's text layer takes 1.4 s; one 512-token chunk takes 12.5 s alone and 15.9 s in a batch. So a 2-core member brain reads about 5 notes a minute, and 1,825 documents are a night's work, not a sitting's.

What the api did meanwhile: the laptop file route was `async` and read the PDF on the event loop. Ten reads of the 300-page PDF on the loop kept `/health` from answering for 13.9 s (the sitting's 15 s); the same reads in a worker thread kept its slowest answer at 0.085 s.

### What changed

1. Reading off the loop, one at a time. `POST /documents/import-laptop/file` extracts and proposes in a worker thread behind a gate of one reader and two waiting (api/import_pace.py `ReadGate`). Beyond that the brain answers 503 with `Retry-After: 5` before the file is charged to the run; the agent sends it again after 2, 4, 8 ... 60 s, up to 8 times, and only then counts it refused ("brain busy"). The exception handler now passes an HTTPException's headers through (it dropped them).
2. Two passes. At the choice (`POST /documents/import-laptop/plan`) the brain makes the first pass: the chosen documents that fit `FIRST_PASS_SECONDS` (15 minutes) of reading at the measured rate, folders the person named first (`"named": [...]`), then files changed in the last 180 days, smallest first; books (PDF or DOCX of 5 MB or more) read overnight unless the person says now (`"big": "now"`). The helper sends in that order (first pass, then the files kept as files, then the rest smallest first), and the approve-all worker reads in that order. At the measured rate the first pass is about 56 notes. (Branch import-manifest-1 proposes a first pass of about 300 files, "measure before choosing the cap": at 15.9 s a chunk 300 notes are about 80 minutes of reading, so the cap here is the 15-minute budget, not a file count.)
3. The second pass reads below chat: the worker thread runs at a lower priority (nice 10), pauses 0.5 s between documents, and waits while a chat ran in the last 8 s (a plain ASGI clock on `/chat*`, at most 2 minutes per document).
4. One true count. `GET /documents/waiting` (owner) counts every pending document proposal (documents and chats apart, by the server's one chat rule, api/chat_continue.py `CHAT_DOC`) and the reading now (done of total, the first pass, an estimate in seconds). The home card and its button read it; the footer (cc-bridge `_pending_live`) reads it. The run's arrivals are counted exactly (`run.counts`) beside the list of the newest 500. The NodeOS page of 1,000 and the bridge's page of 200 are gone.
5. Approve once. "Remember all" sends `{"kind": "documents", "follow": true}`: the server chooses from the full list, keeps the yes on disk (`runtime/remember_all.json`), lets the open run's later files join it as they arrive, resumes it after an api restart, and never queues one proposal twice. The home shows the progress from the server, so a closed browser loses nothing. A proposal the injection scan rated high is still held for a one-by-one look.
6. Refused files. At the end of its run the agent prints them by reason (too big, a type Knowledge does not read, brain busy, no longer on the computer, other) and posts the list (`POST /documents/import-laptop/refused`, the run's token, only names the run listed). The home lists them by reason; "Send these again" (`POST /documents/import-laptop/retry`, owner) or Return in the terminal sends only the retryable ones (brain busy, other); the agent waits 10 minutes for that, then closes the run.
7. What the person sees while it reads: "Reading what matters first: N of M." then "Ready to talk now. Still reading the rest: N of M, about H hours."; at the choice, "12 books, 2.1 GB: read them overnight / now".

The Caddy lines of every member gain `/api/bf/documents/import-laptop/refused` (above and in scripts/add-member.sh); without it the refused list does not reach the home (the run itself is unaffected).

### Not done

- The member manifest's work areas as first-pass folders: the plan route takes `named`, the home does not ask for it yet.
- The container itself was not measured (torch, Postgres writes); the numbers are ONNX on the same core type.
- The Python helper retries a busy brain and posts its refused list, but has no "send these again" wait.
- agent.ps1 was not run (no PowerShell on the build box).
- A faster embedder for 2-core member brains (bge-small, or the embedding spoke) would change the first pass from about 56 notes to several hundred; not changed here, it re-indexes.

## Codex and Claude Code history (MEMBERS-11, 2026-11-23)

hbar 2026-11-23: "An easy way to do import from the Claude and the Codex of the individual, this was one of our main onboarding issues." The coding agents keep their history on the computer, not in an account export: Codex (CLI, IDE extension and desktop app) in `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl`, Claude Code in `~/.claude/projects/<folder slug>/<session>.jsonl`. Both are hidden folders, which every walk skips by rule, and `.jsonl` is not a type Knowledge reads, so before this none of it came in.

### What comes, what never does

- One session file is one conversation document, the same shape as a chat export (`# <title>`, `Source: codex session, conversation <id>`, `Started:`, then `Working folder: <cwd>` when the session names one, then `## Me, <time>` and `## Assistant (Codex)` or `## Assistant (Claude Code)`). File name `codex_<date>_<slug>_<id8>.md` or `claude-code_<date>_<slug>_<id8>.md`; `api/chat_continue.py` knows both prefixes, so Continue here works on them.
- Kept: the person's typed messages and the assistant's visible text replies (Codex commentary and final answers; Claude Code text blocks). An answer split around tool steps becomes one turn. An image the person pasted is `[image]`.
- Dropped by rule: tool calls and their arguments, tool results and command output, reasoning and thinking, system, developer and environment-context messages (`<environment_context>`, `# AGENTS.md instructions`, `<system-reminder>` spans, slash-command and local-command lines), file-history snapshots, summaries, compaction summaries, side chains (Claude Code subagents), API error lines and every meta line. A session with nothing typed (a Codex subagent, a run started by a tool) is no conversation and is not proposed.
- Title: the first typed message, one line, 80 characters. Dates from the line timestamps (UTC).
- Parsers: `codex_conversation()`, `claude_code_conversation()` and `session_conversation()` in `scripts/import_chats.py`; `FORMATS` marks both verified (structure read from real files on the box 2026-11-23, read only; tests use synthetic files only). Codex writes the typed text twice in newer versions (an `event_msg` `user_message` and the `response_item` beside the injected context); the event copy is used when present, else the items.

### Three ways in

1. Bring in this computer (the survey, Door 1): all three walkers (`brain_import.py` `survey()`, `agent.sh`, `agent.ps1`) walk two more labelled roots after the cloud folders: "Codex history" = `<home>/.codex/sessions` and "Claude Code history" = `<home>/.claude/projects` (Windows `%USERPROFILE%\.codex\sessions`, `%USERPROFILE%\.claude\projects`). One list: `AGENT_HISTORY` and `HISTORY_EXT` in `brain_import.py`, rendered into both agents by `api/laptop_agent.py`. Inside these roots only `*.jsonl` is offered (everything else counted as "not a chat"); Claude Code files only at `<slug>/<session>.jsonl` (subagent files and memory folders deeper down are "not a chat"); the 25 MB cap and the secret-name rules hold; hidden files inside stay out. Nothing else under `~/.codex` or `~/.claude` is ever walked: `auth.json`, `config.toml`, `history.jsonl`, `.credentials.json`, `settings.json`, memory files. A link in place of either folder is not followed. The inventory names them `Codex history/2026/11/08/rollout-....jsonl`, `Claude Code history/-Users-sam-code-site/<id>.jsonl` (the label replaces the hidden part, so `clean_relpath` takes them as they are), and `roots` ends with the two labels.
2. The plan (`api/laptop_survey.py`): each label is ONE group, never split, kind knowledge, proposed by default, `why` `codex_history` / `claude_code_history` ("your Codex history, one conversation per session"). Anything under a label that is not a session file is dropped from the inventory.
3. The file route: `POST /documents/import-laptop/file` with a `.jsonl` under one of the two labels takes the chat path (`_import_laptop_session` in `api/main.py`): token checked and charged like any file (25 MB), parsed into one conversation, proposed through `_propose_document_text` under the conversation's own name (not `laptop/...`), so it lands PENDING and keeps its Continue here starting point. The parsed source must match the label (a Claude Code file under "Codex history" is 422); nothing typed is 422; a `.jsonl` anywhere else stays 415. Nothing is remembered before the person's yes.
4. One dropped file: the home chats card and the Knowledge page take a session `.jsonl` (POST /documents/import-chats, the chip "Codex, Claude Code" in `ui/lib/aiExports.js` says where the files are).

The home card says it in one line (`compAgents` in `ui/lib/moveInPlan.js`, en and ru); the agents print `HISTORY` (`WORDS` in `api/laptop_agent.py`) when they found either folder.

### Without a terminal

- Codex desktop app or IDE extension: the same `~/.codex/sessions` folder on the same computer, so the survey line brings it. A person who never opens a terminal can drop one session file on the chats card (Finder: Go, Go to Folder, `~/.codex/sessions`; Windows: `%USERPROFILE%\.codex\sessions` in the Explorer address bar).
- Claude desktop app and claude.ai chats live on Anthropic's servers, not on the computer: those come only through the claude.ai export (Door 2, the Claude chip). Claude Code sessions started from the desktop app are local and live in `~/.claude/projects` like any other.

### Tests

`tests/test_agent_history.py` (synthetic sessions only): both parsers keep typed and visible text and drop tool lines, reasoning and injected context (a secret in a tool result or environment block never reaches the document); the event copy is used once; subagents are no conversation; prep and the chats route take a dropped `.jsonl`; the Python survey offers the session files only (`auth.json`, `config.toml`, `history.jsonl`, `.credentials.json`, `settings.json`, memory and subagent files never listed; secret names, empty and over 25 MB counted); a linked `.codex` is not followed; the plan keeps each history as one knowledge group; the rendered agents carry the roots; `agent.sh` end to end lists exactly what the Python survey lists and brings both sessions as PENDING conversation documents with their Continue here records; the route takes a session under a label and refuses one elsewhere (415), a hidden path (400), no token (401), the wrong tool or nothing typed (422).

### Not verified

- A real Mac and a real Windows laptop with Codex and Claude Code installed (here: Linux, made-up homes).
- `agent.ps1`: checked statically only (rendered roots and words); no PowerShell on the box.
- Older Codex rollouts (before `session_meta` lines) are read by a fallback (the item on the line itself); no such file was on the box to read.

## Other AIs (2026-11-16)

Every AI comes in through the same card and the same gate: `POST /documents/import-chats`, one document per conversation, each one PENDING, one yes.
There is no picker: the file says what it is (`normalize()` and `load_export()` in `scripts/import_chats.py`).
Uploads may be the zip as it came or the bare file inside it (`.json`, `.csv`, `.html`).
Documents keep the shape above: title, `Started:` line, then `## Me, <time>` and `## Assistant (<name>), <time>`; file name `<source>_<date>_<slug>_<id8>.md`.
`FORMATS` in the script holds the same verified/unverified table as below; the console's list of export buttons (English and Russian) is `ui/lib/aiExports.js`.
Unverified means the parser follows third-party descriptions of the file and is written to be tolerant; the first real export of each should be read by hand once.

### Gemini (unverified)

- Button: takeout.google.com, Deselect all, tick My Activity, "All activity data included", Deselect all, tick Gemini Apps, OK, Next step, Create export (https://support.google.com/gemini/answer/16920332). Gems are under the separate "Gemini" product and are not read.
- File: `Takeout/My Activity/Gemini Apps/MyActivity.html` by default, `MyActivity.json` when "Multiple formats" is set to JSON. The folder name is localized, so any `MyActivity.json`/`.html` is read and only records whose header or products say Gemini are kept (a full My Activity export also holds Search, YouTube).
- Record fields `header`, `title`, `titleUrl`, `time`, `products`, `details` are Google's own (https://developers.google.com/data-portability/schema-reference/my_activity). Where the prompt and answer sit is not in Google's docs; the parser takes the prompt from `details` name Request, else a title starting "Prompted ", else `userInteractions[].request` (a serialized json string); the answer from `details` name Response, `safeHtmlItem[].html` (stripped to text) or `userInteractions[].response` (third-party description: https://portable-ai-memory.pages.dev/providers/google/).
- Grouping: My Activity is a flat list of prompt/answer records, not conversations. Records whose `titleUrl` carries a conversation id (`gemini.google.com/app/<id>` or `/app/c/<id>`) are one conversation per id; records without an id start a new conversation after 30 minutes without a record (`GAP_S`). The title is the first prompt.
- The html card is: header, "Prompted <text>", a date line, the answer, "Products:". Its date line is local time without a usable zone and is read as UTC; English month names only (other Takeout languages fall through to "no conversations", then paste).

### DeepSeek (unverified)

- Button: chat.deepseek.com, profile, Settings, Data, Export data (menu names from third-party guides; no DeepSeek doc found).
- File: a zip with `conversations.json`: an array; each has `id`, `title`, `inserted_at`, `updated_at` and a `mapping` tree like ChatGPT's whose messages hold `fragments` typed REQUEST (the person), RESPONSE (the answer), THINK and SEARCH (left out, as ChatGPT's reasoning is). Shape as read by the open-source viewer https://github.com/akivacp/chatgpt-json-tree-viewer.
- Parse: told apart from ChatGPT by `fragments`; main branch from `current_node` if present, else the last child at each step (the latest regeneration).

### Grok (unverified)

- Button: accounts.x.ai/data, Download account data (or grok.com, Settings); the zip comes by email.
- File: `ttl/30d/export_data/<user>/prod-grok-backend.json`: `{"conversations": [{"conversation": {id, title, create_time, modify_time}, "responses": [{"response": {_id, parent_response_id, sender, message, create_time: {"$date": {"$numberLong": ms}}}}]}]}` (https://portable-ai-memory.pages.dev/providers/grok/, and the viewer above). Other files in the zip are ignored.
- Parse: the kept branch ends at the newest leaf of the `parent_response_id` tree; `sender` "human" is the person, anything else (assistant, ASSISTANT, a model name) the answer. Thinking traces, search results and images are left out.

### Copilot (unverified columns)

- Button: account.microsoft.com/privacy, Privacy, Empower your productivity, Copilot, Copilot apps, Export all activity history (personal Microsoft accounts only). Verified: https://support.microsoft.com/en-us/privacy/manage-your-copilot-activity-history-in-the-privacy-dashboard says it downloads a CSV, but not its columns.
- File: a CSV. Columns per https://portable-ai-memory.pages.dev/providers/microsoft/: `Conversation, Time, Author, Message` (Copilot apps), `CreatedAt, MessageContent, Author, ChatName` (Copilot Chat and Microsoft 365 apps; `M/D/YYYY H:MM:SS +HH:MM`), `Timestamp, ClientApp, Prompt` (Windows apps, prompts only). No json export is documented.
- Parse: rows carry no conversation id, so rows are grouped by the Conversation / ChatName value; rows without one start a new conversation after 30 minutes. Author Human/User is the person, anything else the answer.

### Le Chat (unverified)

- Button: admin.mistral.ai/account/export, Export (https://help.mistral.ai/en/articles/347623-how-do-i-export-my-data-from-le-chat; read 2026-11-16 the article names the product "Vibe" and does not describe the file).
- File: not documented. The parser reads json conversations with `chat_messages` (or `messages`) whose items have `role` and `content` (a string or text blocks) and no `sender`, as the viewer above describes Mistral's export; the file name is unknown, so a zip with no known file has every `.json` tried. If nothing is recognised, the person pastes the conversation (the fallback).

### Perplexity (no readable export: fallback)

- No documented bulk file format: the account page (https://www.perplexity.ai/account/details) offers "Export my data" to some accounts, otherwise a privacy request by email; neither documents the file (community thread https://community.perplexity.ai/t/feature-request-bulk-export-of-all-threaded-conversations/371).
- Route: per thread, the ... menu, Export, Markdown or PDF, dropped on the card; or copy and paste. A text naming Perplexity is stored with source `perplexity`.

### Anything else: the pasted fallback (verified, ours)

- The card's `text` field (pasted) or a dropped `.txt`, `.md`, `.html` or `.pdf` (pdf through pypdf, in api/requirements.txt) becomes ONE conversation document through the same gate.
- Turn markers at the start of a line are detected: You, User, Me, Human (and Я, Вы, Пользователь) for the person; ChatGPT, Assistant, AI, Gemini, Claude, Copilot, Grok, DeepSeek, Perplexity, Le Chat, Mistral, Bot, Model (and Ассистент, ИИ) for the answer; also "You said:", "**User:**" and "## Me:". Both sides must appear, else the whole text is one "Me" block.
- Source: the vendor named by the AI markers, else a vendor named in the first 3000 characters (perplexity, le chat, chat.mistral.ai, gemini.google.com, chatgpt.com, claude.ai, ...), else `pasted` (assistant shown as "AI"). Title: the `title` field, the html `<title>` or pdf title, else the first line. Date: the day of import.
- Route form fields now: `file` (optional), `text` (optional), `title` (optional), `newest` (default 50); exactly one of `file` and `text`, else 400. The answer has the same keys as before.

## Bring in this computer: the one line, Mac and Windows (SPOKE-3, 2026-11-16)

hbar 2026-11-16, on SWITCH-1's eight-step Mac flow: "there has to be a standardized way: easy copy this in terminal and then gives full access for the brain to import stuff from the laptop", for members whose laptop he cannot touch (Christos) and for Windows (Elena). This is the member path. SWITCH-1 (inbound SSH over the brain's own network, branch `switch-1`) stays the advanced path for a standing spoke.

### The line

The home card "Bring in this computer" (Door 1 above) mints the survey token and shows one line with Copy:

- Mac (Terminal) and Linux: `curl -fsSL https://<brain>/api/bf/laptop/agent.sh | bash -s -- imp_...`
- Windows (PowerShell): `$env:BRAIN_TOKEN="imp_..."; irm https://<brain>/api/bf/laptop/agent.ps1 | iex`
- In Russian, both addresses carry `?lang=ru` (the agent's own words, `WORDS` in `api/laptop_agent.py`).

The card links "Read what this line runs" to the same address. The key travels in the line, never in the address, so the script is the same text for anyone who fetches it.

### The pattern: the laptop dials out, the brain never dials in

The agent is a short script that calls OUT over HTTPS to the token door of MOVE-IN-2 and nothing else: `GET /documents/import-laptop/check` (key check, then the wait for the choice with `?form=lines`, a text answer for shells that have no JSON parser), `POST /documents/import-laptop/check` (the inventory), `POST /documents/import-laptop/file`, `POST /documents/import-laptop/finish`. The plan, the yes per group and the caps are MOVE-IN-2's, unchanged. No VPN, no SSH server, no Remote Login, no router change, no inbound door: the laptop opens nothing to anyone. That is both fewer steps and a smaller surface than SWITCH-1, which opens SSH on the laptop to the brain.

What one run does: check the key; walk the home folder and the cloud folders (iCloud Drive, `~/Library/CloudStorage/*` for Google Drive, Dropbox, OneDrive and Box, `~/Dropbox`, `~/OneDrive*`, `~/Google Drive`, `~/iCloudDrive`, `<letter>:\My Drive`); send the list (names, sizes, dates; gzip JSON); wait for the yes on the home; send exactly the chosen files, checking each against its own list (a name it did not list is counted and never sent); close the key; delete its temp folder and exit. Ctrl+C closes the key too. It writes no receipt and installs nothing; the home card shows what arrived.

- Mac and Linux: bash 3.2 or later, curl, find, stat (BSD or GNU), awk, gzip, all part of macOS. No Python (on a fresh Mac `python3` only offers to install the developer tools). The whole script is one function called on its last line, so bash reads all of it before running any of it. The key goes to curl from a file in the temp folder (mode 600), never on curl's command line.
- Windows: Windows PowerShell 5.1 as Windows 10 and 11 ship it, .NET HttpClient, no module, no administrator. `irm | iex` runs text, not a script file, so the execution policy does not apply; it turns on TLS 1.2 for its own calls. Links and junctions are not followed (the profile's "Application Data" style junctions); OneDrive's online-only files are listed and download when sent.
- Never-send rules: one list, `SKIP_DIRS` and `SKIP_FILES` of `scripts/import/brain_import.py`, rendered into both scripts by `api/laptop_agent.py` at each fetch (awk regex on the Mac, `-like` on Windows). Also never listed: names with a tab, a newline or a backslash, and names over 400 characters (counted as "name too long or odd").

### macOS privacy, without the Full Disk Access switch

A script run from Terminal reads the home folder as the person. macOS guards Desktop, Documents, Downloads, iCloud Drive and removable volumes per app: the first time Terminal opens one, macOS asks "Terminal would like to access files in your Documents folder", and Allow is one press; the card and the agent say so. A folder refused that way, and anything else macOS keeps closed, is not looked into: the agent names it ("The computer kept these private") and the inventory carries `<folder>: kept private by the system`. Mail, Messages, Safari and the Photos library sit under `~/Library` or in a `.photoslibrary`, which the walk never enters anyway. No Remote Login and no Full Disk Access on this path.

Unverified until a real Mac runs it (the hook is `ops/2026-11-16_switch-1-mac-trial.sh` in hbar.world): which of Desktop, Documents, Downloads and iCloud Drive prompt on the current macOS, whether find waits on the prompt or fails first, and the exact error text.

### The Apple Developer ID is not needed here

A `curl | bash` line is not a downloaded app, so Gatekeeper's "unidentified developer" check never runs (curl sets no quarantine flag). The USD 99 a year Developer ID only removes the Open Anyway step of SWITCH-1's downloaded `Join my brain.app`. On Windows likewise: no downloaded installer, so no SmartScreen prompt and no code signing certificate.

### A standing connection is not built

The agent runs once and is gone. A standing version (re-scan on a schedule, so agents can pick up new files) would add a LaunchAgent on the Mac or a scheduled task on Windows, a long-lived key stored on the laptop, and an auto-updating script: whoever controls the brain's address could then run new code on the laptop on every scan, without the person pasting anything. That is a separate decision with its own card; this path keeps "you pasted it, it ran once, it is gone".

### The two routes and Caddy

`GET /laptop/agent.sh` and `GET /laptop/agent.ps1` (api/main.py): public, no state, `Cache-Control: no-store`, text. The brain's address in the script comes from the request's Host (`https://<host>/api/bf`; validated as a plain host name; behind the console's own proxy, which sees `api:8000`, from the X-Forwarded-Host it sets). Listed in `tests/test_sec_pass_1_routes.py` `PUBLIC_SCRIPT_DOORS`, awaiting hbar's review. The Caddy snippet above opens them beside the four token paths; an existing box needs the two paths added to both `path` lines of its console block (the central thread applies it on hbar's word).

### Tests

`tests/test_laptop_agent.py`: the line run as the member runs it (curl piped to bash) against the api on 127.0.0.1 over a temp home with planted secrets and made-up cloud folders; its inventory equals the Python survey's name for name; the chosen files arrive, pictures and music kept as files; a brain asking for names it was not offered gets none of them; refusals (no key, unknown key, a folder-by-folder key, a non-https address); the line replaced while waiting; odd names, links and a locked folder; Russian; the routes, the address rule and the text form of the check; the awk secret regex against fnmatch. agent.ps1 is checked statically only: no PowerShell on the box (the auto-mode classifier refused fetching one on 2026-11-16).

### Not verified

- A real Mac: the privacy prompts above, BSD find and stat on a large home, the time it takes.
- A real Windows laptop (Elena's): the whole of agent.ps1. What the test needs: Windows 10 or 11, a member brain with a survey token and the Caddy paths open, PowerShell from the Start menu, the line pasted; watch for TLS errors on the first `irm`, Defender or SmartScreen prompts, OneDrive online-only files, Cyrillic names, and the time for a full profile.
