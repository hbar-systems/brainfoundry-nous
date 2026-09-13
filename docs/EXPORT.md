# Export and restore (the one command)

Created: 2026-09-13 (unreleased 0.10.0). Companion: `docs/BACKUP_RESTORE.md`
(rotating on-box backups) and `scripts/export_brain.py` / `scripts/import_brain.py`
(the laptop-side, SSH-driven pair from Track G). This page is the buyer-facing
version: one command or one button, on the brain, no laptop tooling.

## What you get

One `.tar.gz` named `brain-export-<brain_id>-<UTC>.tar.gz`:

| path in the archive | what | restored by |
|---|---|---|
| `manifest.json` | format `brainfoundry-brain-export/v1`, brain id and version, embedding model and dimension, row counts, list of what is inside | read first by `import_brain.py` |
| `db/document_embeddings.jsonl` | the memory: every chunk, its metadata, its embedding | `scripts/import_brain.py` |
| `db/chat_sessions.jsonl`, `db/chat_messages.jsonl` | chats | `scripts/import_brain.py` |
| `persona/brain_persona.local.md` | the personalized identity | `scripts/import_brain.py` (or Persona tab paste) |
| `md/*.md` | every governance `.md` in the runtime volume (persona, charter, pack `.md`) | copy back by hand (step 4 below) |
| `config/brain_identity.yaml` | non-secret identity config | reference only |
| `apps/installed.json` | the installed-apps registry: id, repo, pinned commit sha, permissions, layers, the packs record | re-install (step 3 below) |
| `peers/peers.json` | introduced federation peers | copy back by hand (step 5 below) |

Deliberately not inside, so the file is safe to email, store, or hand over:
`.env`, provider API keys, the settings sidecar (`settings.json`, which holds
operator secrets encrypted with `BRAIN_IDENTITY_SECRET`), NodeOS secrets, the
brain private key, audit logs, quarantine state. The build refuses to write an
archive that contains any of those names, wherever they came from.

Not inside either: NodeOS `memory_proposals` (they live in the nodeos
container's sqlite, unreachable from the api container). `scripts/export_brain.py`
still collects them over SSH if you need them.

## Make one

Console: Settings, Export, "Export my brain", then Download. The archive is
also kept under `/app/runtime/exports/` on the brain until you delete it
(Settings lists them; `DELETE /export/<name>` removes one).

Shell on the brain host:

```
scripts/export.sh                 # -> ./brain-export-<id>-<UTC>.tar.gz
scripts/export.sh ~/exports       # -> into that directory
```

API (operator key):

```
curl -sS -X POST -H "X-API-Key: $BRAIN_API_KEY" https://<brain>/export
curl -sS -H "X-API-Key: $BRAIN_API_KEY" https://<brain>/export/<name> -o brain.tar.gz
```

Inside the api container the same thing is `python -m api.export [--out DIR | --stdout]`.

## Restore onto a brain

The target is any BrainFoundry brain (a fresh one from the provisioner, or a
self-hosted one). Restore REPLACES the target's memory, chats and persona; it
is not a merge. Take a backup of the target first if it holds anything.

1. Memory, chats, persona (from your laptop; needs SSH to the target):
   ```
   scripts/import_brain.py <target_host> brain-export-<id>-<UTC>.tar.gz
   ```
   The manifest's embedding dimension is checked; a mismatch loads content
   with null embeddings and re-embeds with the target's own model
   (`scripts/reembed_null_embeddings.py`). Expect minutes per thousand chunks
   on a CPU box.
2. Keys and settings: re-enter provider keys in Settings, Keys. They were never
   in the archive.
3. Apps: for each entry in `apps/installed.json`, install it again. Either
   the pack way (`POST /apps/packs/<name>/install` for each name under
   `packs`), or per app: Apps page, install from `repo`; the brain pins the
   current HEAD, so if you need the exact old build pass `ref` = `commit_sha`
   to `POST /apps/install`. Permissions and layers are re-approved at install,
   which is the point.
4. Governance `.md`: copy `md/*.md` into the target's runtime volume
   (`docker compose cp md/. api:/app/runtime/`), then rebuild or restart the
   api so the persona reloads.
5. Peers: copy `peers/peers.json` to `data/peers.json` in the api container,
   or re-introduce each peer from the Federation tab (which also re-pins the
   pubkey; the safer path).
6. Verify: `/health` 200, `/identity` shows your brain id, Knowledge tab
   shows the document count from the manifest, Apps tab shows the apps, a
   chat answers from your corpus.

Identity note: a restore keeps the TARGET brain's keypair and `BRAIN_ID`. A
moved brain is therefore a new federation identity; peers must re-introduce it.
