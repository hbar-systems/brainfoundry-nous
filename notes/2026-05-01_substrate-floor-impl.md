---
created: 2026-05-01
domain: federation trust mechanisms
session_type: implementation
---

# Substrate Floor (Layer 1) — Implementation Session

DATE: 2026-05-01
DOMAIN: federation trust mechanisms
SESSION TYPE: implementation

## KEY INSIGHTS

- Storage chose Postgres, not SQLite. The brain already runs Postgres for
  `document_embeddings`, `chat_messages`, `federation_inbox`, etc. Adding a
  separate SQLite file would split the persistence layer. The spec allowed
  Postgres ("unless there is a strong reason to do otherwise"); the strong
  reason is consistency.
- Attestation granularity is **per artifact**, not per chunk. The RAG store
  shreds documents into many `document_embeddings` rows, but the attestation
  ledger records ONE row per ingested artifact (`document_name`-keyed) with
  `content_hash` over the full source text. That keeps `artifact_count`
  meaningful — 50 chunks of one journal entry shouldn't satisfy the floor.
- The signing payload for an attestation excludes `timestamp_ingested` (set
  by the DB clock). This makes backfilled signatures deterministic and
  reproducible from reconstructed text.
- Two ingestion paths needed hooks: chat consolidation
  (`/chat/sessions/{id}/consolidate`, api/main.py:971) and document upload
  (`/documents/upload`, api/main.py:1420). Both call
  `substrate.record_attestation_safe(...)` after the existing chunk-write
  block — the safe wrapper swallows ledger errors so a misconfigured floor
  never blocks RAG ingestion.
- The substrate-depth gate is env-toggleable via
  `FEDERATION_SUBSTRATE_GATE=off`. Default `on`. The endpoint
  (`/federation/substrate-depth`) is always served regardless, because peers
  can ask non-destructively without forcing trust.
- Per-peer fetch result is cached (5 min default) so the handshake gate
  doesn't re-fetch a candidate's depth on every assertion. Combined with
  the candidate's own 5-min payload cache, two brains exchange at most one
  substrate-depth round-trip per 5 min.

## OPEN QUESTIONS — surfaced for operator (probability of recommendation)

### Q1 — first_person_attestation enforcement

Implemented option (a): owner-trust marking. Both ingestion paths set
`first_person_attestation="authored_by_owner"` by default. There is no
per-artifact override yet. Adding one is a 5-line change to the upload
form when wanted.

- (a) owner-trust marking — **shipped, ~85% recommend**
- (b) source-domain check — defer until Layer 1 alone proves insufficient (~10%)
- (c) authorship inference / stylometry — explicitly excluded (~0%)

Action: confirm (a) is acceptable for v0; flag if you want a per-artifact
override exposed in the upload form.

### Q2 — backfill for existing brains

Migration script implemented, **not run** —
`scripts/substrate_backfill.py`. Defaults to DRY-RUN. Reconstructs
documents from `document_embeddings` (chunks joined by `\n`), classifies
`chat-*` as `conversation` and the rest as `document`, labels everything
`authored_by_owner` unless `--label-derived <pattern>` is passed. Records
each row with `backfilled=true`.

- (a) auto-backfill, `backfilled=true` — **script ready, ~90% recommend**
- (b) require re-ingestion — friction-heavy, not recommended (~5%)

Action: review proposed plan, then run on **yury-brain first**, observe,
roll to hbar-brain and e2e if results are clean.

```
# Recommended sequence (per prompt §sequencing.8):
ssh <yury-brain-host>
cd /opt/brainfoundry-nous   # or wherever the deployment lives
git pull
python scripts/substrate_backfill.py            # dry-run, review summary
python scripts/substrate_backfill.py --commit   # apply
curl -s https://yury.brainfoundry.ai/federation/substrate-depth | jq .
# verify counts make sense, then repeat for hbar-brain, then e2e.
```

### Q3 — handshake-flow integration shape

Existing handshake (`POST /v1/federation/assertion`, api/main.py:310) is
already pinned-peer-only, fail-closed for unknown endpoints. The
substrate floor was added as an **additive gate**: after sig/replay/jti
all pass, the issuer's `/federation/substrate-depth` is fetched (over
their `issuer_endpoint`), the depth payload is verified against the
**same pinned pubkey** from `known_peers.toml` (never against the depth
payload's self-published `brain_pubkey` field — preserves T1 closure),
and the floor is applied. On floor failure, the handshake returns 403
with a machine-readable code.

This means the gate trips on **every** assertion from a peer who passes
the handshake but doesn't yet have substrate. That's intentional — the
peer is genuinely "in the federation" only when their substrate clears
the floor, and the cache makes the cost negligible.

### Q4 — threshold defaults

Used the prompt's defaults (50/25/2/7d). Surfaced via `GET
/settings/federation` so operators can inspect at runtime without
reading env. If a legitimate brain trips the floor in testing, prefer
seeding test brains over silently lowering thresholds.

## DECISIONS MADE

- Postgres-backed `artifact_attestations` table.
- Per-artifact granularity, hash over full source text (not per chunk).
- Signing payload excludes timestamp so backfilled rows are deterministic.
- Gate default = on, env toggle to off.
- Per-peer fetch cached 5 min (env: `SUBSTRATE_PEER_CACHE_SECONDS`).
- Floor failure = HTTP 403 with `{ok, code, details}` body.
- `substrate_depth_unreachable` is its own code (distinct from
  `substrate_floor_not_met` / `signature_invalid`) so operators can tell
  whether the peer is offline vs. genuinely thin.
- Default `first_person_attestation = authored_by_owner` at ingestion.
- Backfill script is DRY-RUN by default.

## BELIEF UPDATES

- Initial intuition was SQLite-per-brain (per the prompt's preferred
  default). After reading the codebase, Postgres-backed wins on
  consistency: the brain never runs without Postgres anyway, and the DM
  layer's pattern of `init_tables()` at startup is right next door.
- Confirmed that the existing handshake is *already* fail-closed via
  `find_peer_by_endpoint` — adding the substrate gate did not change
  the trust assumptions, only added a freshness check. This was an
  important sanity check: I am not weakening the existing flow.

## DELIVERABLES

| File | Purpose |
|------|---------|
| `api/substrate.py`                            | New module — ledger DDL, sign, verify, threshold check, peer fetch+cache. |
| `api/main.py`                                 | Hooked: startup (init_tables), `/v1/federation/assertion` (gate), `/federation/substrate-depth` (new public endpoint), `/settings/federation` (introspection), 2× ingestion-path attestation calls. |
| `scripts/substrate_backfill.py`               | DRY-RUN backfill migration; pass `--commit` to apply. |
| `tests/test_substrate.py`                     | 13 tests covering acceptance criteria 1–7 (live-DB criterion 8 gated on `SUBSTRATE_PG_TEST=1`). |
| `tests/__init__.py`                           | Empty — makes `tests` a package. |
| `.env.example`                                | Documented all 7 new env vars. |
| `README.md`                                   | New "Federation trust — substrate floor" section. |
| `notes/2026-05-01_substrate-floor-impl.md`    | This note. |

## ACCEPTANCE TEST RUN

```
$ pytest tests/test_substrate.py -v
========================= 12 passed, 1 skipped in 2.60s ==========================
```

The 1 skipped test (`test_8_persistence_roundtrip`) is the live-DB
integration — opt-in via `SUBSTRATE_PG_TEST=1 DATABASE_URL=...`.

## OPEN ITEMS — do before merging

1. **Operator approves Q1, Q2, Q3, Q4** as recorded above.
2. **Run live-DB test** against a staging Postgres:
   ```
   SUBSTRATE_PG_TEST=1 DATABASE_URL=postgres://… pytest tests/test_substrate.py::test_8_persistence_roundtrip -v
   ```
3. **Backfill yury-brain** (per Q2 plan), verify
   `/federation/substrate-depth` returns sensible counts.
4. **Confirm gate behavior on yury ↔ hbar handshake** end-to-end:
   - Pre-backfill on candidate: assertion should 403
     `substrate_floor_not_met`.
   - Post-backfill: assertion should succeed.
5. **Iterate threshold defaults** if any legitimate brain trips the
   floor — surface to operator before lowering.
6. **CHANGELOG entry** before tagging the next version.

## LINKS

- Design rationale: hbar.world/discussions/2026-05-01_federation-trust-mechanisms.md
- Public framing: hbar.world/marketing/posts/2026-05-01_founders-curse-self-correction.md
- Implementation prompt: hbar.world/ops/prompts/2026-05-01_brainfoundry-substrate-floor.md
- Constitutional grounding: hbar.world/systems/hbar.economy/repos/site/HBAR.ECONOMIC.CORE/chapters/6_Governance_Measurement.md and §B13
