# brain-apps/

Created: 2026-05-06

Installable apps for a BrainFoundry brain. Each app is a standalone GitHub
repository conforming to the `brain-app/v1` manifest dialect.

## Concept

A brain is a sovereign cognitive substrate. Apps are how the substrate gains
new surfaces. An installed app:

- adds a tab to the brain UI nav,
- runs as a sandboxed iframe served at `/apps/<id>/`,
- talks to the brain through a postMessage bridge,
- declares its memory-layer access and permissions in `brain-app.yaml`,
- is approved by the operator at install time.

Manifest schema: `registry/schema/brain/app.schema.json` (in hbar.world).
Worked example: `registry/schema/brain/app.example.yaml`.

## Files in this directory

- `installed.json` — the registry of installed apps. Source of truth on disk.
  Read at brain startup; tabs and routes are mounted from it.
- `<id>/` — clone of an installed app (gitignored). Created by the install
  pipeline; never hand-edited.

## Installing an app (v0)

Two paths, both call the same backend:

1. UI: Settings → Apps → paste GitHub URL → Approve.
2. Power-user: clone the app repo into `brain-apps/<id>/`, then call
   `POST /apps/install` with `{ "path": "brain-apps/<id>" }`.

A successful install:

1. Validates `brain-app.yaml` against the manifest schema (hard gate).
2. Checks tab.route does not collide with built-in routes.
3. Mints an app token (used by the iframe bridge for permission-checked calls).
4. Appends an entry to `installed.json` with the pinned commit SHA.
5. Hot-mounts the app's static bundle and API router (or schedules a brain
   restart in v0 if hot-mount is not yet wired).

## Sandboxing posture

Iframes are loaded with `sandbox="allow-scripts allow-same-origin"`. Same-origin
is required for the postMessage bridge without CORS gymnastics. Permission
enforcement is server-side: the host shell holds the app token, the iframe
posts intents (e.g. `memory.write`) through the bridge, the host calls the
brain API with the app token, and brain middleware checks the token's
declared-permission scope against `installed.json` before executing.

A v1 hardening pass will tighten sandbox flags (cross-origin isolation, CSP,
Trusted Types) once the bridge schema settles.

## Why apps are pre-built bundles, not built-at-install

A typical brain runs on a 4-8GB ARM VM. Cloning a Next.js app and running
`npm install && npm run build` at install time is slow and OOM-prone. App
authors ship a `dist/` (or equivalent) directory in-tree. The install
pipeline only clones at a pinned commit SHA and serves the static dir.

## License

Apps installed into a brain must be open-source-compatible with the brain's
own license (AGPL-3.0). The manifest's `license` field is the install-time
check.
