# Upgrade note: an existing 0.9.4 brain receiving 0.10.0 (packs, export, first-use)

Created: 2026-09-13. For the operator running the Update tab on a live brain
that is on 0.9.4 plus the autonomy commit (3b1e67c). First run: the operator's
own brain `hbar` (CAX11, self-update enabled 2026-07-31 via
docker-compose.override.yml with BRAIN_HOST_DIR set). Written before the
branch is merged; the Update tab pulls `origin/main`, so nothing below happens
until central merges `packs` into main and pushes.

## Before pressing Update

1. Central bumps `VERSION` to `0.10.0` and dates the CHANGELOG heading in the
   merge commit (docs/VERSIONING.md). If that is skipped, `/health` and
   `/identity` keep saying 0.9.4 after the update and the only proof of the
   new code is the commit shown in the Update tab.
2. Note the current commit shown in the Update tab (expected 3b1e67c). That is
   the rollback point `update_brain.sh` writes to `.update-prev-commit`.
3. Disk: `df -h /` on the box. The update builds new images (api and ui) and
   the first export later writes under the `api_runtime` volume. A CAX11 with
   under 3 GB free should be pruned first (operator approval; SERVERS.md).
4. Optional but recommended on hbar: take a manual `scripts/backup_brain.sh`
   in addition to the automatic pre-update snapshot (the Update tab path does
   snapshot; the SSH one-liner does not).

## What the Update tab does (scripts/update_brain.sh, unchanged by 0.10.0)

Pre-update snapshot to `.brain-backups/pre-update/`, backs up `.env`, stashes
any local edits, `git pull --ff-only origin main`, restores runtime files,
records the rollback commit, `docker compose build`, recreates nodeos, ui and
public-chat, hands the api recreate to a helper container, waits for `/health`.
Budget on a CAX11: 3 to 8 minutes, most of it the ui build. If the ui build
fails (a JS error in the new pages), `set -e` stops the script before any
container is recreated and the old containers keep serving; the tab shows the
build log.

## What changes on disk

In the checkout (`/home/hbar/brain`), all from git:

| path | change |
|---|---|
| `brain-apps/packs/base.json` | new: the base pack (six defaults plus oracle at v0.1.0) |
| `brain-apps/defaults.json` | comment only; now a compatibility alias |
| `brain-apps/.gitignore` | tracks `packs/` |
| `api/schemas/brain-pack.schema.json` | new |
| `api/schemas/brain-app.schema.json` | optional `compute` block |
| `api/apps.py` | pack loader, seeder reads `BRAIN_PACKS`, `/apps/packs` endpoints, `compute` recorded |
| `api/export.py`, `scripts/export.sh`, `docs/EXPORT.md` | new: the export |
| `api/onboarding/first_use.py` | new; `GET /onboarding/first-use` in `api/main.py` |
| `api/main.py` | mounts the export router and the first-use endpoint |
| `docker-compose.yml` | `BRAIN_PACKS=${BRAIN_PACKS:-base}` in the api environment |
| `.env.example`, `CHANGELOG.md`, `brain-apps/README.md`, `docs/BACKUP_RESTORE.md` | docs |
| `ui/pages/index.js`, `ui/pages/upload.js`, `ui/pages/settings.js` | first-use checklist, ten-files banner, key guide, Export panel |

Not changed: `.env` (BRAIN_PACKS is absent there; compose defaults it to
`base`), `docker-compose.override.yml`, the persona in the runtime volume,
`brain-apps/installed.json`, the database, the peers file.

Runtime state after the update:

- `brain-apps/installed.json`: untouched. `seed_default_apps()` sees the
  `defaults_seeded` marker every established brain already carries and returns
  before reading any pack. No `packs` key is added; no app is installed.
- `/app/runtime/exports/`: created on the first export, inside the
  `api_runtime` named volume. Each archive is the whole corpus; delete old
  ones from Settings.

## What to check after (10 minutes)

1. `/health` 200; `/identity` shows the version (0.10.0 if central bumped it)
   and the same `brain_id` and pubkey as before.
2. Update tab shows the new commit; the previous one is in `.update-prev-commit`.
3. Persona intact: Persona tab shows the operator's text, not the template.
   (The J1 split keeps it in the runtime volume; this update does not touch it.)
4. Apps unchanged: `GET /apps/list` (or the Apps page) lists the same apps as
   before. `GET /apps/packs` (operator key) lists `base` with `missing` naming
   whichever base apps this brain lacks (on hbar that is expected to be
   `oracle`, and any default the operator uninstalled). Nothing was installed.
5. Export smoke: Settings, Export, "Export my brain". Expect an archive of a
   few tens of MB on hbar (thousands of chunks with 1024-dim embeddings).
   Download it, `tar tzf`, confirm `manifest.json`, `db/`, `persona/`,
   `apps/installed.json` are present and no `settings.json` or `.env`.
   Then delete it from Settings if disk is tight.
6. Dashboard: for an established brain `GET /onboarding/first-use` returns
   `complete: true` and `fresh: false`; no checklist renders and no app opens
   on its own. If the card does render, the brain has fewer than ten documents
   or no key set, which is the intended reading.
7. Knowledge tab: no ten-files banner when the brain holds ten or more
   documents.
8. Chat: one question answered from the corpus. Model unchanged (hbar's
   override pins Sonnet BYOK; untouched).

## Optional after the checks (operator approval, it clones repos onto the live brain)

`POST /apps/packs/base/install` adds the base apps this brain lacks (oracle),
install-if-absent, hot-mounted. Or the Apps page, install
https://github.com/hbar-systems/brain-app-oracle by hand.

## Rollback

Update tab, "Revert to previous version" (`scripts/revert_brain.sh`, one step
back to `.update-prev-commit`), or the pre-update snapshot with
`scripts/restore_brain.sh` (docs/BACKUP_RESTORE.md). Nothing in 0.10.0 touches
the database schema, so the revert is code-only.
