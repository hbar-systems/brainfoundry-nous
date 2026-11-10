---
created: 2026-11-10
---

# Week

The owner's week page on one screen, so it can open by itself beside the conversation.

## What it does

- Asks the host page for `week/index.html` on the owner's Files desk (`files.read`). On hbar's brain that is `/cc/files/raw/home/hands/out/week/index.html`, written by hbar.world's `scripts/week-page.py`.
- Shows the page as it is, full size. It reads it again when the tab comes back into view.
- Links in the page that point at this console open there: a thread (`/talk?thread=...`) opens the conversation, a desk file (`/cc/files/raw/...`) opens in Files. Other links do nothing (an app cannot open popups).
- No page on the desk (404 or 403): one line, "No week page on this brain yet. hbar.world's scripts/week-page.py writes it."

## Permissions and why

- `files.read`: the one desk file above. The host refuses `..`, absolute paths and anything outside the desk.

No memory layers, no model calls.

## Install

Shipped with the template in `brain-apps/shipped/week/` and in the base pack, so a fresh brain has it. On a running brain: Update the brain, then press Install beside Week under "Shipped with this brain" at /apps. To open it when you sit down, answer `week` to the interview's first question, or set `start` to `/apps/week` at /layout.
