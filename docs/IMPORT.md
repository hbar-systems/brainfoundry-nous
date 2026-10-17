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
