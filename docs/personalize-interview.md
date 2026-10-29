# Personalize the console: the interview

Created: 2026-10-09. Read by the brain's reasoner (CC) when the owner asks to set up or personalize the console, or on first use if they want to. The question list is fixed and lives in `scripts/cc/cc_layout.py` (`QUESTIONS`); a test keeps this file and that list in step. Amended 2026-10-29: starts from a preset.

## Start from a preset (2026-10-29)

The interview no longer starts from the stock console. It starts from a preset (the catalog in `docs/PERSONALIZATION.md`, the files in `scripts/cc/presets/`), and the ten questions only adjust it.

- Ask first, in one sentence, which of these the person is: the owner who runs the brain (`owner`), a member of an organisation brain (`org`). The other two presets are not interviewed: `family-telegram` has no console, and `public` is a public chat page. If the brain's operator already chose a preset, use it and do not ask.
- Then ask only the questions whose answer the person wants different from the preset. A preset's answer stands unless the person changes it; an unanswered question keeps the preset's answer (or the stock default when the preset has none).
- Name the preset in the block (below). Never invent a preset name; the bridge refuses one that is not a file in `scripts/cc/presets/`.

## How to ask

- Up to ten questions, in this order, only those that adjust the preset. One or two at a time, in plain sentences, in the owner's language. Do not read the list out like a form.
- Offer the options in the words below. Accept anything that clearly means one of them. If an answer is unclear, ask once more, then leave that question unanswered (the stock default stays).
- The owner may skip any question. Skipped means unanswered; do not guess.
- Never ask for, or write, CSS, colours as free text, URLs or file paths. The layout is a closed list of choices.

## The questions

| id | ask | options (value: words) |
|---|---|---|
| first | What do you open first when you sit down? | talk: the conversation; gallery: my conversations as a deck; panes: several conversations side by side |
| never | Which of these do you never use? Say none if all stay. (several allowed) | board; gallery; files; sidebyside: side by side; handsfree: the hands-free row; hint: the starter hints; hero: the title block |
| panes | When the brain opens a screen for you, one at a time beside the chat, or several? | one; several |
| side | Which side should the pane sit on? | right; left |
| tone | Black, light, or the stock warm dark? | black; light; default: stock |
| face | Serif, mono or sans for the conversation? | serif; mono; sans |
| weight | Thin type or normal? | thin; normal |
| size | Text small, normal or large? | small; normal; large |
| width | Narrow column, wide, or the full width? | narrow; wide; full |
| voice | Voice: off, answers read aloud, or hands-free? | off; speak: read aloud; handsfree: hands-free |

## How the answers become the layout

When you have the answers, end one message with exactly one block, using the option values from the table (values, not the words), and only for questions that were answered, with the preset when one was chosen:

```
<layout>{"preset": "owner", "answers": {"first": "talk", "never": ["board", "gallery"], "panes": "one", "side": "right", "tone": "black", "face": "mono", "weight": "thin", "size": "normal", "width": "narrow", "voice": "off"}}</layout>
```

- `never` is a list (empty list for none). Every other answer is a single string.
- `preset` is optional; without it the answers adjust the stock console, as before.
- The bridge turns the preset and the answers into the layout file with `from_answers` (this is the `layout.apply` step) and stores it as a proposal. It does not apply. Say in the same message that the layout is waiting and that the owner presses "apply" on the card (or at /layout).
- A block that does not validate is refused with the reason, shown to the owner. Do not retry with invented keys.
- After applying, the owner can change any answer later at /layout (the same chips), or press "save layout" in the console footer to store how the console looks right now.

## What the answers change

| answer | effect in the console |
|---|---|
| first | the page the console opens on: the conversation, /gallery or /panes (once per browser session) |
| never | the named block is hidden; "reset layout" and /layout bring it back |
| panes: one | hides the "side by side" button |
| side | the pane opens left or right of the conversation |
| tone | colour preset: black, light, or the stock palette |
| face | serif is Lora, mono is JetBrains Mono, sans is the system sans |
| weight, size | thin type (font weight 300); text zoom 0.92, 1, 1.12 |
| width | the conversation column: 860px, 1180px, or the full width |
| voice | answers read aloud on or off; hands-free on or off |

Accent and the other colour variables are not asked; the owner sets them at /layout from a short list.
