# Naming — public standard

Created: 2026-07-02
Updated: 2026-07-03 (operator ruling: public product name is **BrainFoundry**;
`nous` is reserved as a brain *instance* name, not the product)

The project accumulated several names for the same things during development
(`brainfoundry-node`, `brainfoundry-nous`, `BrainFoundryOS`, `BrainKernel`,
`NodeOS`, `nodeos`, `nous`, `Nous`). For the public launch we standardize on
**one** public name for the product and **one** for the governance kernel.
This file is the source of truth for prose.

## The standard

| Concept | Public name (use in docs/prose) | What it is |
|---------|--------------------------------|------------|
| The product / platform | **BrainFoundry** (formerly styled *BrainFoundryOS* — drop the "OS") | The self-hosted sovereign-AI product and the federation protocol its brains speak. This is the brand. |
| A running install (this repo) | **a BrainFoundry brain** (or *node*) | One installed instance: FastAPI + Next.js + Postgres/pgvector + Docker Compose. "Run your own BrainFoundry brain." |
| The governance kernel | **BrainKernel** | The authority kernel that gates the chat loop with caller-bound permits, routes brain-layer mutations through propose → approve → execute, and keeps the append-only audit log. Internally the container/env identifier is `nodeos`. |
| An individual brain's name | e.g. **nous** | `nous` is the name of the operator's own personal brain instance (it also backs the public demo at `nous.brainfoundry.ai`). Brains are named per-instance like sailboats — `nous` is one such name, **not** the product. |

Rules for docs going forward:

- Say **BrainFoundry** for the product/platform. Not "Nous", not "brainfoundry-node".
- Say **a BrainFoundry brain** (or *node*) for a single running install.
- Say **BrainKernel** for the governance kernel. Do **not** introduce "NodeOS"
  in new prose — it is retained only as the internal container/env identifier
  (`nodeos`), noted below.
- Use **nous** only as an example/instance name (the operator's brain, the public
  demo). Never as the product name.

## Follow-up: code / container renames (NOT applied)

These are the identifiers that still say `node` / `nodeos`. Renaming them is a
**breaking, coordinated** change — every deployed brain's `.env`, compose file,
and inter-service calls reference them. They are intentionally **left as-is** for
this release and listed here as a tracked follow-up. Do not rename piecemeal.

| Identifier | Where | Rename to | Blast radius / why deferred |
|-----------|-------|-----------|------------------------------|
| `nodeos` (compose service name) | `docker-compose.yml` | `brainkernel` | Referenced by `NODEOS_URL=http://nodeos:8001` and depends_on across services; renaming breaks every running brain's service discovery until all redeploy. |
| `NODEOS_URL`, `NODEOS_INTERNAL_KEY`, `NODEOS_SIGNING_SECRET`, `NODEOS_HMAC_SECRET`, `NODEOS_PUSH_BRANCH_ALLOWLIST` | `.env.example`, compose, `nodeos/main.py`, `api/main.py` | `BRAINKERNEL_*` | Every operator's `.env` sets these; a rename needs a compat shim reading both old and new names for ≥1 release. |
| `nodeos/` (directory + `nodeos/main.py`) | repo root | `brainkernel/` | Dockerfile build context path; changing it touches compose `build.context`. |
| `brainfoundry-node` (README H1 / prose) | `README.md` | `BrainFoundry` | Prose only — **applied in this release.** |
| container/host paths `/home/hbar/brain`, `BRAIN_HOST_DIR` default | compose, docs | (unchanged) | Operator-specific default; not a naming issue, left alone. |
| repo name `brainfoundry-nous` | GitHub | (keep) | The `-nous` suffix reads as "the reference/first brain instance"; harmless, no change. |

Recommended sequencing when this is picked up: ship a release where the code
reads BOTH `NODEOS_*` and `BRAINKERNEL_*` (old names as fallback), migrate
`.env` files across the fleet, then remove the old names a release later.
