---
created: 2026-05-02
domain: federation trust mechanisms
session_type: rollout
---

# Substrate Floor (Layer 1) — Rollout Session

DATE: 2026-05-02
DOMAIN: federation trust mechanisms
SESSION TYPE: rollout
SUMMARY: Layer 1 shipped to main (commits `339e2da`, `cc1961c`),
deployed to yury/e2e/hbar via `git archive` rsync, federation registry
populated on 3 of 4 brains, gate verified live end-to-end with
`hbar → yury` returning HTTP 403 `substrate_floor_not_met` with
per-check breakdown. Federation ring is now gate-armed and ready for
forward attestation.

## Live verification (the canonical demonstration)

```
$ ssh hbar 'docker compose exec api python /app/scripts/fed_sign.py --audience yury'
eyJhbGciOiJFZERTQSIsInR5cCI6IkJSQUlOX0ZFRF9BU1NFUlRJT04i...

$ curl -X POST https://yury.brainfoundry.ai/v1/federation/assertion \
    -H 'Content-Type: application/json' \
    -d '{"token":"...","issuer_endpoint":"https://hbar.brainfoundry.ai"}'

HTTP 403
{
  "ok": false,
  "code": "substrate_floor_not_met",
  "details": {
    "artifact_count":     {"got": 0, "required": 50},
    "first_person_count": {"got": 0, "required": 25},
    "source_diversity":   {"got": 0, "required": 2},
    "age_days":           {"got": null, "required": 7}
  }
}
```

End-to-end path exercised: `find_peer_by_endpoint` (registry hit) →
ED25519 signature verify against pinned pubkey → replay cache → jti
check → `fetch_and_check_peer` (HTTPS to hbar's signed depth payload)
→ `verify_depth_payload` (signature against same pinned pubkey, T1
closure preserved) → `check_floor` → 403 with structured body.

## Rollout sequence

| Step | Action | Result |
|------|--------|--------|
| 1 | Endpoint rename `/federation/substrate-depth` → `/v1/federation/substrate-depth` | Slots into existing Caddy `/v1/federation/*` exemption — no per-host Caddyfile diff |
| 2 | Live-DB test on throwaway docker Postgres | 1 passed (test_8_persistence_roundtrip) |
| 3 | Surgical extract of substrate-floor hunks from mixed working tree (concurrent public-chat session) → commit `339e2da` | 8 files, +1464/-2; 6 substrate hunks in api/main.py preserved verbatim, +169 public-chat hunk restored to working tree afterward |
| 4 | rsync `git archive HEAD` → yury (65.21.247.227) → docker compose up → backfill | yury: 1 attestation backfilled (`consciousness_quantum_measurement.md`, 8655 B, kept) |
| 5 | rsync → e2e (62.238.16.142) | e2e: 0 docs in corpus; backfill is no-op |
| 6 | rsync → hbar (77.42.23.35); dry-run showed 5 drafted docs | **`--commit` skipped per operator's "everything or nothing" principle** — drafts not canonized |
| 7 | Populate `known_peers.toml` on 3 brains; `hbar→yury` live curl test | 403 `substrate_floor_not_met` ✓ |
| 8 | CHANGELOG entry | Commit `cc1961c` |
| 9 | This note | Done |

## Federation ring substrate state (post-rollout)

| Brain | Endpoint | artifact_count | source_diversity | first_person | oldest_ts | Floor | known_peers.toml |
|-------|----------|---:|---:|---:|------|------|------|
| yury  | https://yury.brainfoundry.ai | 1 | 1 | 1 | 2026-04-15 | FAIL | populated (3 peers) |
| e2e   | https://e2e.brainfoundry.ai  | 0 | 0 | 0 | — | FAIL | populated (3 peers) |
| hbar  | https://hbar.brainfoundry.ai | 0 | 0 | 0 | — | FAIL | populated (3 peers) |
| nous  | https://api.nous.brainfoundry.ai | (not queried — separate session) | ? | ? | ? | ? | **pending sudo cleanup** |

All four brains run with `FEDERATION_SUBSTRATE_GATE=on` (default).

## Operator design decisions recorded this session

### "Everything or nothing" — clean brain principle

Operator: *"either we push everything as the quantum brain experiment
says, we only push one or nothing."* hbar's 5 drafted docs (chat
exports + early HBAR/YURY/MASTER_CONTEXT planning notes) were not
canonized into the substrate ledger. The operator will manually delete
the underlying RAG content from hbar and re-ingest deliberately later;
the auto-attestation hooks will record those re-ingests as
`backfilled=false` with deterministic ED25519 signatures over the
canonical row payload.

This makes the substrate ledger an **authoritative forward record** —
every row represents content the operator deliberately authorized as
canonical. `backfilled=true` rows (only yury's 1 row, kept by operator
choice) are flagged distinct from real ingest.

### Gate stays `on` everywhere

Discussed `GATE=off` as a soft-launch option (option B in the rollout
chat). Rejected: the unit-test suite already proves the gate logic;
shipping `gate=on` exercises the full network path under real
conditions and surfaces any unknown external callers immediately.
Federation DM is unaffected (separate code path).

### Federation registry as deliberate trust

`known_peers.toml` populated as a deliberate trust decision per the
file's own schema: pubkeys verified out-of-band against each brain's
`/identity` and `/v1/federation/substrate-depth` outputs.

| Brain | pubkey (b64url, 32 chars) |
|-------|----|
| yury  | `_NyMlZbmJGg4JHRslXrUz6fbgTFYzWwbbuzOwwMQk5o` |
| nous  | `g1f_3sdYDuBFpEopB_BcEMaYMv3MGFXD-C6OFIGS_Gs` |
| e2e   | `LHPeSRPPnBY9pSFLbRqMWDK3-9tv7NsMxFc9HbSj7h4` |
| hbar  | `7fsmF0655EF2HddmqYgU19Oz9hvrwb5LIebVGaIEktc` |

When friend's brain is provisioned: operator adds a 5th entry to
each existing brain's `known_peers.toml` and writes a fresh
`known_peers.toml` on the new brain pinning the other four.
`peers.py` re-reads on every request (no restart).

## Cross-session coordination

A second Claude Code session was running concurrently, building the
public-chat surface for `nous` (`apps/public-chat/`, `/v1/public/chat`,
`PublicRateLimiter`, Caddy three-vhost split). Both sessions edited
`api/main.py` independently in the same working tree.

Coordination steps:

1. Surgical extract: this session saved the mixed `api/main.py` to
   `/tmp/main.py.mixed`, reverted to clean HEAD, re-applied 6
   substrate hunks via Edit calls, committed `339e2da`, restored the
   mixed file. Public-chat session's working tree was undisturbed.
2. Operator held the public-chat session idle during the ~30s extract
   window (zero race risk).
3. Public-chat session shipped `f18e976` (their own commit on top of
   `339e2da`) and `git push`'d both commits to origin/main together.
4. This session's rsyncs to yury/e2e/hbar sourced from `git archive
   HEAD`, not the working tree — so they got substrate-floor only,
   not the public-chat additions still uncommitted at the time.

## Operational debt — surfaced for follow-up

### nous — sudo cleanup needed

Pre-existing condition (timestamp Apr 19, before either Claude
session): an empty root-owned directory at
`/home/hbar/brain/api/identity/known_peers.toml` got baked into nous's
docker image at some earlier build. Renders the registry as `[]`
(empty list — fail-closed correct behavior, but blocks federation).

**Operator action:**

```bash
ssh -i ~/.ssh/id_ed25519_brainfoundry_automation hbar@62.238.4.20
sudo rm -rf /home/hbar/brain/api/identity/known_peers.toml
exit

# Then from laptop:
scp -i ~/.ssh/id_ed25519_brainfoundry_automation \
  /tmp/known-peers/nous.toml \
  hbar@62.238.4.20:/home/hbar/brain/api/identity/known_peers.toml

ssh -i ~/.ssh/id_ed25519_brainfoundry_automation hbar@62.238.4.20 \
  'cd /home/hbar/brain && docker compose cp api/identity/known_peers.toml api:/app/api/identity/known_peers.toml && docker compose restart api'
```

After: nous joins the federation registry; the gate works in all four
directions of the ring. (`/tmp/known-peers/nous.toml` was generated
this session; recreate from scratch if `/tmp` is cleared.)

### Dockerfile — `COPY scripts /app/scripts/` missing

Backfill script (`scripts/substrate_backfill.py`) and federation
test scripts (`fed_sign.py`, `fed_verify.py`) live on disk in
`/home/hbar/brain/scripts/` but are NOT inside the api image. Workaround
this session: `docker compose cp` each at runtime. Future operator-run
backfills hit the same workaround.

**Recommended fix (separate PR):** add `COPY scripts /app/scripts/`
to `api/Dockerfile` so all scripts are included at build time.

### Floor success path not yet demonstrable

All four brains have substrate-depth below the floor. The 403 rejection
path is verified live; the 200 success path requires at least one brain
to reach `artifact_count >= 50`, `first_person >= 25`,
`source_diversity >= 2`, `oldest_artifact_ts >= 7d ago`. This is
operator-paced via real ingestion; auto-attestation hooks now record
every new artifact going forward.

When a brain crosses the floor: federation assertions issued from that
brain will succeed; thinner brains continue to be rejected. The floor
is per-issuer, asymmetric — receive-only state is a real and valid
federation membership tier.

### Caddy XFF + federation endpoint paths on nous

The other session's Caddy reload moved nous's brain API from
`nous.brainfoundry.ai` → `api.nous.brainfoundry.ai`. Federation peers
must use the `api.` subdomain for `/v1/federation/*` calls. The
populated `known_peers.toml` files reflect this. Any external CLI
clients that still target the bare `nous.brainfoundry.ai` for
federation will 404 on `/v1/*` paths until they update config.

## What this session does not include

- Pushing untested code to remote (anti-goal #3 — not violated; both
  commits `339e2da` and `cc1961c` were operator-approved before
  pushing). The `cc1961c` push is pending if not yet pushed.
- nous corpus seeding (other session's follow-up).
- nous CLI defaults migration (other session's follow-up).
- `known_peers.toml` for any additional brains beyond the current 4
  (when friend's brain provisions, operator adds the 5th entry).
- Threshold tuning. Defaults 50/25/2/7d kept per Q4 approval; if
  legitimate brains trip the floor in unexpected ways, surface and
  decide rather than silently lower.

## Links

- Implementation note: `notes/2026-05-01_substrate-floor-impl.md`
- Implementation prompt: `hbar.world/ops/prompts/2026-05-01_brainfoundry-substrate-floor.md`
- Rollout prompt: `hbar.world/ops/prompts/2026-05-02_substrate-floor-merge.md`
- Design rationale: `hbar.world/discussions/2026-05-01_federation-trust-mechanisms.md`
- Public framing: `hbar.world/marketing/posts/2026-05-01_founders-curse-self-correction.md`
- Concurrent session note: `notes/2026-05-02_nous-public-chat-impl.md`
- Constitutional grounding: HBAR.ECONOMIC.CORE Ch.6 §6.6, Appendix B §B13
