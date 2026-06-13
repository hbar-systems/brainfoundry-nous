# Backup & Restore

A brain holds its owner's accumulated cognition. The vector DB and a handful of
per-brain runtime files are **not in git** and cannot be regenerated — lose them
and the brain's memory is gone. This is the safety net under that risk.

Two scripts, both sovereign (everything stays on the owner's box, nothing phones
home):

- `scripts/backup_brain.sh` — produces one timestamped, restorable artifact.
- `scripts/restore_brain.sh` — brings a brain back from one artifact.

## What's in an artifact

Each run writes a directory under `BACKUP_DIR` (default `/home/hbar/brain-backups`):

```
<BACKUP_DIR>/daily/20260613T031500Z/
  db.sql.gz        # pg_dump of the whole vector DB (incl. document_embeddings)
  runtime.tar.gz   # settings.json, brain_persona.local.md, peers.json,
                   #   federation_audit.jsonl, tool_audit.jsonl, brain-apps/,
                   #   governance audit — the state that is NOT in git
  manifest.txt     # timestamp, git HEAD, version, row counts
```

**Secrets are deliberately excluded.** No `.env`, no API keys, no private key —
same rule as `scripts/export_brain.py`. An artifact is safe to copy around. On a
fresh-box restore you supply `.env` yourself (you already keep it somewhere safe;
it is the one thing only the owner has).

## Backups

```bash
# A normal backup (also handles retention + weekly promotion):
scripts/backup_brain.sh

# Snapshot taken automatically before every update/rebuild (see below):
scripts/backup_brain.sh --pre-update --label "<commit>"
```

**Retention** (oldest pruned, every prune logged — never silent):

| Category     | Kept (default) | Override        |
|--------------|----------------|-----------------|
| `daily/`     | 7              | `DAILY_KEEP`    |
| `weekly/`    | 4              | `WEEKLY_KEEP`   |
| `pre-update/`| 10             | `PREUPDATE_KEEP`|

One daily per ISO week is hard-linked into `weekly/` (no extra disk).

### Schedule it (host cron — simplest, sovereign)

```cron
# nightly at 03:15, append to a log on the owner's box
15 3 * * *  /home/hbar/brain/scripts/backup_brain.sh >> /home/hbar/brain-backups/backup.log 2>&1
```

A compose sidecar would also work, but host cron is the v0 recommendation: one
line, on the owner's machine, no extra container.

## Pre-update snapshots (the important one)

`scripts/update_brain.sh` (the in-container "Update" tab path) calls
`backup_brain.sh --pre-update` **before** it pulls and rebuilds. A bad deploy
then costs minutes, not a brain. Because that script runs inside the api
container — where `/home/hbar/brain-backups` is not mounted — those snapshots
land under `<BRAIN_DIR>/.brain-backups/pre-update/` instead (the brain dir is
bind-mounted, so they survive the rebuild). It is best-effort: a failed snapshot
warns but does not block the update. Set `REQUIRE_BACKUP=1` to make a missing
snapshot abort the update instead.

If you deploy the fleet way — the laptop one-liner that does
`git reset --hard origin/main && docker compose up -d --build` (SERVERS.md) —
that path runs entirely on the remote host and does **not** auto-snapshot. Take
one first:

```bash
ssh <brain-host> "cd /home/hbar/brain && scripts/backup_brain.sh --pre-update --label pre-deploy"
```

## Restore — the fresh-box runbook

The restore is the half people skip. Prove it on a scratch box, not just that the
dump runs.

1. **Get the artifact onto the box** (or it's already there from a local backup):
   ```bash
   scp -r mylaptop:/path/to/20260613T031500Z  /home/hbar/restore-artifact
   ```

2. **Check out the repo and supply `.env`** (the one secret not in the artifact):
   ```bash
   git clone <repo-url> /home/hbar/brain
   cd /home/hbar/brain
   cp /your/safe/place/.env .env       # API keys, BRAIN_PRIVATE_KEY, secrets
   ```

3. **Bring the stack up** (creates empty volumes + schema):
   ```bash
   docker compose up -d --build
   ```

4. **Restore from the artifact:**
   ```bash
   scripts/restore_brain.sh /home/hbar/restore-artifact
   # type 'restore' to confirm; --force to skip the prompt
   ```

   It replays `db.sql.gz` into Postgres, untars `runtime.tar.gz` back into the
   api container, restarts api, and confirms `/health` + the embedding row count.

5. **Verify:** open the console, check that chats, documents, settings, persona,
   and peers are all present. The row count printed at the end should match the
   manifest.

### Restoring in place (rollback after a bad deploy)

Same command against a `pre-update/` snapshot — the stack is already up, so skip
steps 1–3:

```bash
# host cron snapshots:
scripts/restore_brain.sh /home/hbar/brain-backups/pre-update/<TS>
# Update-tab snapshots (in-container path):
scripts/restore_brain.sh /home/hbar/brain/.brain-backups/pre-update/<TS>
```

## Out of scope (v0)

- Off-box / encrypted remote backup — local rotating + a proven restore first.
- Postgres point-in-time / WAL archiving — overkill at this scale.
