# Import: a year of ChatGPT or Claude into the brain

Created: 2026-10-13. Plan and gap list: hbar.world `ops/2026-10-13_onboarding-import.md` (gaps A to G).
Tool: `scripts/import_chats.py`. Tests: `tests/test_import_chats.py` (synthetic fixtures only).

One rule: the person brings the material, the brain never goes looking for it.
Nothing in this path writes memory directly; every document goes through the same permit, propose, approve gate as a Knowledge-tab upload.

## 1. Get the export (the person's own button)

- ChatGPT: chatgpt.com, Settings, Data controls, Export data. The mailed zip holds `conversations.json` (a top-level array; each conversation is a `mapping` tree of messages), sometimes sharded as `conversations-000.json`, `-001`, ...
- Claude: claude.ai, Settings, Privacy, Export data. The zip holds `conversations.json` (an array; each has `name`, `created_at`, `chat_messages` with `sender` and `text`), `projects.json` and `users.json`.

The zip comes to the brain through the console's Files upload, not by email.

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

A year of chats swamps a fresh brain (hbar's own 943 ChatGPT conversations were about 8.5M tokens).
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

## 7. Design sketch, not built: inbox and sorter (loose folders)

No laptop scan; the person picks folders on their own spoke or drops files into one inbox.

- Inbox: `library/inbox/` in the person's world, filled by the console's Files upload or a synced folder. Nothing outside it is read.
- Sorter: an agent on the brain lists the inbox (name, size, type, first lines; no execution, no following links) and writes `library/inbox/MANIFEST.proposed.tsv`: path, proposed place (`areas/<area>/`, `library/<date>_<source>/`, or `stays-outside`), kind, size, reason, remember yes or no, sha256. Anything that reads as someone else's private material (other people's health records, passwords, IDs, bank exports, sz-type employer material) is proposed `stays-outside` and never offered for memory.
- Review: the console shows the proposed manifest as cards, one per folder, not per file; the person moves or strikes rows, then gives one dated yes.
- File and remember: files move to their places; rows marked remember go through steps 4 and 5 above unchanged (same permit, same manifest id, same hash check). The rest stays as files the brain opens on request.
- Hours from the plan: inbox and sorter 4, card review 3, pick-folders on the spoke 2.
