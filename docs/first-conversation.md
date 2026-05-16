# The first conversation

*Created 2026-05-15. Updated 2026-05-16 — Track J1 persona file split.*

This is the example first conversation that ships with every brain. It is the
cold-start fix: a fresh brain has an empty Knowledge tab and a persona that
still reads `[BRAIN_NAME]` / `[OWNER_NAME]`, and a new owner has no idea what
to do first. This walkthrough gives them a concrete first move — naming the
brain and writing its identity — before they ever upload a document.

The console renders a condensed version of this walkthrough as the chat
empty-state whenever the persona is still the unconfigured template (see
`ui/pages/chat.js`, the `IdentityOnboarding` panel). This file is the
canonical long-form copy — keep the two in sync when either changes.

---

## What the brain says first

> **Welcome. I'm your brain — but I don't have a name yet.**
>
> Right now I'm running the unedited template persona. Before we really get
> started, two things define me:
>
> 1. **My name** — what you'll call me.
> 2. **Your name** — who I belong to and answer to.
>
> Use the **Name your brain** button above. It fills both into my persona
> document, strips the template banner, and reloads me as a named brain. It
> runs the same step the provisioner runs by hand — you just don't need a
> terminal for it.

## After naming

The persona is split across two files (Track J1):

- `api/brain_persona.template.md` — the tracked blank template. Always carries
  the `[BRAIN_NAME]` / `[OWNER_NAME]` placeholders. A `git pull` updates it;
  it never holds a brain's real identity.
- `api/brain_persona.local.md` — the personalized copy, written by the **Name
  your brain** button (or `scripts/personalize_persona.py`). Gitignored and
  rsync-excluded, so updating the brain can never overwrite its identity.

The runtime loads `.local.md` if it exists, otherwise the template. Once
named, `api/brain_persona.local.md` is the brain's system prompt on every
turn — keep editing *that* file. The owner is encouraged to do so; the
template leaves clear sections for:

- **Who you are** — background, work, what you're building.
- **Cognitive style** — how you think, how you want answers shaped.
- **Projects** — what's active, what matters right now.
- **Language preferences** — tone, register, what to avoid.

The more specific the persona, the more the brain stops sounding like a
generic assistant and starts sounding like *yours*.

## Then: feed it

Naming is identity. Knowledge is substance. The natural next step after this
conversation is the **Knowledge** tab — upload writing, notes, research,
past conversations. Every chat can also be saved back into memory with
**Save to memory**, which embeds the conversation into the episodic layer so
future chats retrieve from it.

## Why this ships in the template

`get-a-brain` (the public self-serve path) depends on a new owner being able
to go from "fresh instance" to "named brain with a real identity" without
reading docs or opening a terminal. This walkthrough is that path.
