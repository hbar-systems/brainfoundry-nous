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
| nous  | https://api.nous.brainfoundry.ai | (separate session) | ? | ? | ? | ? | populated (3 peers) |

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

### nous — orphan directory resolved

Pre-existing condition (timestamp Apr 19, before either Claude
session): an empty root-owned directory at
`/home/hbar/brain/api/identity/known_peers.toml` got baked into nous's
docker image at some earlier build. Rendered the registry as `[]`.

**Resolved this session.** `rmdir` from the `hbar` user worked without
sudo — the directory was empty and the parent was hbar-owned, so the
rmdir was governed by parent-directory write permission. No password
needed. Then `scp` the populated TOML to the freed path and rebuild
the api image (`docker compose up -d --build api`) to bake the new
file in place of the old empty-dir layer. Verified via
`hbar → nous` curl test: `403 substrate_floor_not_met` with
per-check details — registry working, gate path live, ring complete.

Lesson for future docker-compose work on this fleet: never let
docker-compose create a missing bind-mount source as a directory.
Always `touch` the file first or remove the bind-mount line if the
file is supposed to be image-baked.

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

## Principles & FAQ (recorded post-rollout for future operators)

### Why a substrate floor at all?

The federation primitives (DM, assertion) are open by design. Without
a check, an attacker spins up 10,000 empty fake brains, floods the
network with junk DMs and fake assertions, and federation becomes
worthless — same problem email had with spam. The floor is the
cost-to-attack: a spammer would have to ingest real artifacts on each
fake brain across 7+ days, which is infeasible at scale. Layer 1
closes the spam hole before someone notices it's there.

### Doesn't checking another brain's substrate violate sovereignty?

No. The check is metadata-only and mutual-choice on both sides.

**What the substrate-depth payload reveals:** `artifact_count`,
`total_bytes`, `oldest_artifact_ts`, `newest_artifact_ts`,
`source_diversity`, `first_person_count`, `computed_at`, `signature`.

**What it does not reveal:** the artifacts themselves, content hashes,
hashes of any content, the operator's identity, ingestion patterns,
artifact titles, or any link to the operator's life.

**Sovereign choices preserved:**

- **Receiving brain decides** whether to publish the endpoint at all
  (the gate is env-toggleable; the endpoint is also operator-disable-able).
- **Issuing brain decides** whether to publish substrate-depth (a brain
  that doesn't is simply rejected by peers using gates — that is the
  brain's sovereign right to refuse disclosure).
- **Each receiver decides** their own thresholds. Different peers can
  set different floors. No central authority dictates.

It's the credit-score model, not bank-statement disclosure. The
metadata is the language; both sides choose whether and how to use it.

### Why is the manual `known_peers.toml` not just a UX bug to fix?

Because the *whole point* of the file is that pubkeys arrive
out-of-band — phone, signed message, in person — *before* federation
begins. Auto-populating from a peer's `/identity` HTTP endpoint
re-introduces the **T1 flaw** (issuer impersonation) the file is
specifically designed to prevent: an attacker who controls DNS or
hijacks B's URL serves a fake `/identity` with the attacker's pubkey,
and A trusts it. The whole trust model collapses.

Manual = trust. Friction is the security feature, not a wart.

This is the federation analogue of SSH `known_hosts` (which itself
grew an auto-add-on-first-use prompt only with explicit fingerprint
disclosure, not blind trust).

### What does the substrate floor actually count?

Only ingested artifacts attested in the local ledger. Two paths
populate it automatically today:

| Action | Source type | First-person tag |
|--------|-------------|------------------|
| Chat session consolidated (`/chat/sessions/{id}/consolidate`) | `conversation` | `authored_by_owner` |
| Document uploaded (`/documents/upload`) | `document` | `authored_by_owner` |

Defined source types in the schema (for future hooks): `journal`,
`note`, `document`, `conversation`, `work_output`, `other`. Currently
only `conversation` and `document` are wired up automatically; the
others would need new ingestion paths or manual recording.

To cross the floor (50 / 25 / 2 / 7d) a brain needs:

- ≥50 total ingestions (any mix of chats + uploads)
- ≥25 of those tagged `authored_by_owner` (default for owner-driven ingests)
- At least 2 distinct source types (1 chat + 1 doc satisfies)
- Oldest attestation ≥7 days old (real-world clock)

Practical: use the brain ~weekly for ~7 days, do ~50 things, mix
chats and docs.

### How does friend-onboarding work?

Three steps, universal for any new brain joining the network in
Layer 1:

1. **Provision the brain** via `brainfoundry-provisioner-01`. The new
   brain comes online with its own ED25519 keypair and `/identity`
   endpoint.
2. **Out-of-band pubkey exchange.** Friend tells operator their
   `brain_id` and `public_key` over a channel the operator trusts
   (signal, voice, in person, signed email). This is the trust step.
3. **Mutual `known_peers.toml` edit.** Operator adds a 4-line
   `[[peer]]` block on each of their brains; friend adds entries for
   each of operator's brains. `peers.py` re-reads on every request —
   no restart needed.

After step 3: federation DM works immediately between them.
Federation Assertion (the substrate-floor-gated path) works once each
brain has crossed the floor (≥50/25/2/7d).

### Why doesn't this scale beyond trust circles?

It doesn't scale to internet-mesh today, by design. v0 (Layer 1) is
**deliberately** trust-circle scale — friends, colleagues, family —
because that's what's safe to ship without sponsor staking and
probationary minting.

Layer 2 (probationary minting cap) and Layer 3 (vouching with sponsor
stake) are the scaling answer:

- **Layer 2:** new brains join on probation with capped minting
  power, full power earned by substrate accrual + behavior.
- **Layer 3:** existing brains stake reputation to admit new ones;
  bad sponsorship has cost.

Both designs live in `hbar.world/discussions/2026-05-01_federation-trust-mechanisms.md`.
Both are designed but not yet built; implementation lives in
`hbar.economy`, a separate repo. Layer 1 (this rollout) is a
**prerequisite** for Layers 2 and 3 — they both need a "what counts
as real substrate" answer to build on. Today's work is foundational
to the scaling answer, not a permanent ceiling.

## Links

- Implementation note: `notes/2026-05-01_substrate-floor-impl.md`
- Implementation prompt: `hbar.world/ops/prompts/2026-05-01_brainfoundry-substrate-floor.md`
- Rollout prompt: `hbar.world/ops/prompts/2026-05-02_substrate-floor-merge.md`
- Design rationale: `hbar.world/discussions/2026-05-01_federation-trust-mechanisms.md`
- Public framing: `hbar.world/marketing/posts/2026-05-01_founders-curse-self-correction.md`
- Concurrent session note: `notes/2026-05-02_nous-public-chat-impl.md`
- Constitutional grounding: HBAR.ECONOMIC.CORE Ch.6 §6.6, Appendix B §B13
