# Versioning

*Created 2026-05-05.*

## Source of truth

The `VERSION` file at the repo root is the single source of truth.
`api/main.py` reads it at startup into `BRAIN_VERSION`. Don't hardcode
the version anywhere else — every other surface that needs the version
(API responses, the Update tab, kernel command output) reads it through
`BRAIN_VERSION`.

## Format

Semantic versioning: `MAJOR.MINOR.PATCH`.

- **PATCH** — fixes only. No new endpoints, no behavior changes the
  buyer would notice.
- **MINOR** — backward-compatible additions. New endpoints, new tabs,
  new optional config. Existing operators upgrade with no migration.
- **MAJOR** — breaking changes. New required env vars, removed
  endpoints, schema migrations operators must run. Every major needs an
  upgrade-notes section in `CHANGELOG.md`.

## Bumping

When you ship a feature or fix that goes into a new tagged release:

1. Edit `VERSION` to the new number. One line, trailing newline.
2. Add a CHANGELOG entry headed `## X.Y.Z — YYYY-MM-DD — short title`.
3. Commit `VERSION` + `CHANGELOG.md` together with a `chore(version):`
   prefix. Example: `chore(version): bump to 0.8.3 — fix N`.
4. Build and deploy the container — `BRAIN_VERSION` will refresh on
   the next api startup. No code change needed elsewhere.

## Build-time commit hash

The Update tab also displays the **commit** the running container was
built from. That value comes from a separate Docker build-arg
(`BRAIN_GIT_COMMIT`) baked into an env var inside the api image. The
plumbing is in `api/Dockerfile` (`ARG BRAIN_GIT_COMMIT`) and
`docker-compose.yml` (`args: { BRAIN_GIT_COMMIT: ${BRAIN_GIT_COMMIT:-unknown} }`).

Since 2026-09-22 `scripts/update_brain.sh` exports `BRAIN_GIT_COMMIT` and
`BRAIN_BUILD_TIME` before the build, and the Dockerfile bakes them in its
last layer, so a new commit costs one cheap layer. `/admin/version-info`
reports `running` (the baked commit), `checkout` (git HEAD on the host)
and `api_built_at`; `current` is `running` when known, else `checkout`
(images built before this change carry "unknown"). The Update tab's
success test is: the checkout moved, and the running api matches it or
the script said the api image was unchanged (then the container is
correctly kept). If you build by hand:

```sh
BRAIN_GIT_COMMIT=$(git rev-parse HEAD) docker compose up -d --build
```

## What about pre-0.8.2 history?

Versions before 0.8.2 weren't consistently tagged in code. The
`BRAIN_VERSION` constant sat at `0.5.0` from initial scaffolding through
the federation handshake, the substrate floor work, and several layers
of UI additions — without ever being bumped. CHANGELOG entries before
2026-05-02 carry only their date.

The 0.8.x line is anchored at federation runtime (per SERVERS.md
"Runtime version: node-v0.8.0" for yury-brain-01, deployed when
federation went live). 0.8.2 represents the substrate-floor-shipped
state. Earlier in-tree versions exist only as commit history, not as
released tags.
