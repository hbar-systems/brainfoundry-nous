# brain-apps/

Created: 2026-05-06

Installable apps for a BrainFoundry brain. Each app is a standalone GitHub
repository conforming to the `brain-app/v1` manifest dialect.

## Concept

A brain is a sovereign cognitive substrate. Apps are how the substrate gains
new surfaces. An installed app:

- adds a tab to the brain UI nav,
- runs as a sandboxed iframe served at `/apps/<id>/`, in an opaque origin (since 2026-10-16, see "The sandbox" below),
- talks to the brain through a postMessage bridge,
- declares its memory-layer access and permissions in `brain-app.yaml`,
- is approved by the operator at install time.

Manifest schema: `registry/schema/brain/app.schema.json` (in hbar.world).
Worked example: `registry/schema/brain/app.example.yaml`.

## Bridge intents

_(intent catalog — last updated 2026-10-16, adds `storage.*`; 2026-05-18 added `llm.complete`)_

An installed app talks to the brain by `postMessage`-ing an intent to its host
shell (`ui/pages/apps/[id].js`) and awaiting a `reply`. The wire shape:

```
iframe -> host:  { type: <intent>, payload: <object?>, request_id: <string> }
host -> iframe:  { type: 'reply', request_id, ok: <bool>,
                   result?: <object>, error?: { code, ... } }
```

Permission-gated intents are checked first-line in the host shell against the
manifest's `permissions` (and, where relevant, `requires_layers`); server-side
enforcement at the brain API is the durable gate.

| Intent | Permission | Payload | Result |
|---|---|---|---|
| `ping` | — | — | `'pong'` |
| `meta.app_info` | — | — | `{ id, name, version }` |
| `meta.brain_info` | — | — | `{ name }` |
| `memory.write` | `memory.write` + `requires_layers` | `{ layer, content, source?, metadata?, privacy? }` | `{ id, doc_name, privacy }` |
| `llm.complete` | `llm.invoke` + `requires_layers` | `{ messages: [{role, content}, ...] }` | `{ text, model, sources: [...] }` |
| `storage.set` / `storage.remove` / `storage.clear` | — (the app's own store only) | `{ key, value }` / `{ key }` / `{}` | `{ saved: true }`; sent for you by the `localStorage` shim |

### `llm.complete`

Asks the brain to generate a completion. The brain answers over its own
ingested corpus (RAG) using the operator's currently selected (BYOK) model —
the app does not pick a model and never holds a key.

- **Payload:** `{ messages: [{ role: 'system'|'user'|'assistant', content }, ...] }`.
  `messages` must be a non-empty array.
- **Result:** `{ text, model, sources }` — `text` is the generated completion,
  `model` is the model that produced it, `sources` lists the corpus documents
  retrieved.
- **Retrieval scope:** RAG is restricted to the `read`-mode layers the app
  declared in `requires_layers` and the operator approved at install. An app
  cannot generate over a layer it did not declare.
- **Trust:** the host shell mints a loop permit (NodeOS `POST /v1/loops/request`,
  attributed `app:<id>`) and proxies it to the brain `POST /chat/rag`. The
  permit `permit_id` / `permit_token` are held in the host shell — the iframe
  never sees them.
- **v0 limitation:** non-streaming — the full completion returns in one reply.
  SSE streaming is a follow-up.

## The sandbox (2026-10-16): what an app may and may not do

An app runs in an iframe sandboxed with `allow-scripts allow-downloads` and no
`allow-same-origin`, and its files are served with
`Content-Security-Policy: sandbox allow-scripts allow-downloads`. The app's
document has an opaque origin (`self.origin === "null"`) wherever it is
opened. The console's proxy holds the owner's API key and refuses every request
from an app frame (403 `app_frame_refused`), except the app's own files and the
app's own backend, which go without the key. The finding and the fix are in
`THREAT_MODEL.md` section 4b.

What this means when you write an app:

- **Talk to the brain only through the bridge.** `window.parent.postMessage(msg, '*')`
  (or with `location.origin` as the target, which is the console's origin) and
  wait for the `reply` with your `request_id`. Replies come from the console's
  origin. `fetch('/api/bf/...')`, `/cc/...`, `/api/permit` and
  `window.parent.<anything but postMessage>` do not work.
- **Your own files load as before**, by relative URL: scripts, module scripts
  (Vite builds included), stylesheets, images, `fetch` of your own JSON, GLB or
  wasm, and `Worker`s (classic and module) from your own files.
- **`localStorage` works** through a shim the console puts first in your
  HTML: the console keeps it for your app id (at most 2,000,000 characters),
  and it is there again on the next visit. It is synchronous and per app; no
  other app and not the console sees it. `sessionStorage` lasts for the page.
- **Not available:** IndexedDB, cookies, service workers, forms
  (`allow-forms` was never on: use `onClick`, not `type="submit"`), popups and
  top-level navigation.
- **Fonts:** a `@font-face` file in your bundle is fetched without the
  console's login and fails behind basic auth. Inline it (`data:` URL; for Vite,
  raise `build.assetsInlineLimit`) or load it from a public CDN such as Google
  Fonts. The same holds for images that script creates with
  `crossOrigin = 'anonymous'` from your own files.
- **Backends** (`entries.api`) still run inside the brain's API process with
  its authority. The sandbox does not cover them; operators should read them.

Apps written before 2026-10-16 that used only the bridge need no change and no
reinstall. On first load the console copies the keys the default-shelf apps kept
in the console's own storage (`daybook:*`, `hbar-ink-*`, `qr-progress`) into
that app's store.

## Files in this directory

- `installed.json` — the registry of installed apps. Source of truth on disk.
  Read at brain startup; tabs and routes are mounted from it.
- `<id>/` — clone of an installed app (gitignored). Created by the install
  pipeline; never hand-edited.

## Packs (added 2026-09-13, unreleased 0.10.0)

A pack is a domain bundle: brain-apps plus tool ids, governance `.md` files,
and an optional compute spoke. Files live at `packs/<name>.json`, validated
against `api/schemas/brain-pack.schema.json`, each with its own `version`.

- `packs/base.json` is what every instance ships with: the former
  `defaults.json` shelf plus oracle. Always installed. `defaults.json` stays as
  a compatibility alias and is read as base only when `packs/base.json` is
  absent.
- First run: `seed_default_apps()` reads `BRAIN_PACKS` (comma list, default
  `base`, base always first), resolves `requires` in dependency order, and
  installs every listed app through the normal clone-validate-register path.
  The first-run contract is unchanged: once per brain (`defaults_seeded`),
  never on a populated `installed.json`, fail-soft per app and per pack.
  Results are recorded under `installed.json` -> `packs`.
- Later: `GET /apps/packs` lists the shipped packs and their state;
  `POST /apps/packs/<name>/install` installs one on a running brain
  (requirements first, install-if-absent, memory untouched).
- `compute` (pack level, and the optional `compute` block in a brain-app
  manifest) declares a spoke: `endpoint`, `permit_class`, `health_path`. In
  this version it is recorded and shown, not dispatched; a changed compute
  block on update counts as a scope change. Hub, not mesh: the brain calls the
  spoke under a permit; the iframe never does; spokes never call each other.
- `tools` and `md` are declared in this version and not yet acted on.

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
