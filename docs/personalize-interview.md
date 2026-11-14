# Personalize the console: the interview

Created: 2026-10-09. Read by the brain's reasoner (CC) when the owner asks to set up or personalize the console, or on first use if they want to. The question list is fixed and lives in `scripts/cc/cc_layout.py` (`QUESTIONS`); a test keeps this file and that list in step. Amended 2026-10-29: starts from a preset. Amended 2026-11-06: "never" can hide the console's chrome (the quiet console). Amended 2026-11-10: "first" can be week (the Week app beside the conversation). Amended 2026-11-12: the quiet console also folds the four asks and the idle line; the console's own words follow the bridge's `lang` key (en, ru), set beside the layout, not asked here. Amended 2026-11-13: an eleventh question, after the look questions, picks the ways of working the home shows (`surfaces`).

## Start from a preset (2026-10-29)

The interview no longer starts from the stock console. It starts from a preset (the catalog in `docs/PERSONALIZATION.md`, the files in `scripts/cc/presets/`), and the eleven questions only adjust it.

- Ask first, in one sentence, which of these the person is: the owner who runs the brain (`owner`), a friend with a brain of their own (`member`), a member of an organisation brain (`org`). The `public` preset is not interviewed: it is a public chat page. If the brain's operator already chose a preset, use it and do not ask.
- Then ask only the questions whose answer the person wants different from the preset. A preset's answer stands unless the person changes it; an unanswered question keeps the preset's answer (or the stock default when the preset has none).
- Name the preset in the block (below). Never invent a preset name; the bridge refuses one that is not a file in `scripts/cc/presets/`.

## How to ask

- Up to eleven questions, in this order, only those that adjust the preset. One or two at a time, in plain sentences, in the owner's language. Do not read the list out like a form.
- Offer the options in the words below. Accept anything that clearly means one of them. If an answer is unclear, ask once more, then leave that question unanswered (the stock default stays).
- The owner may skip any question. Skipped means unanswered; do not guess.
- Never ask for, or write, CSS, colours as free text, URLs or file paths. The layout is a closed list of choices.

## The questions

| id | ask | options (value: words) |
|---|---|---|
| first | What do you open first when you sit down? | talk: the conversation; gallery: my conversations as a deck; panes: several conversations side by side; doors: a few doors, one for each thing I do here; today: Today (calendar, mail, tasks) beside the conversation; week: Week (the week page) beside the conversation |
| never | Which of these do you never use? Say none if all stay. (several allowed) | board; gallery; files; sidebyside: side by side; handsfree: the hands-free row; hint: the starter hints; hero: the title block; nav: the row of buttons at the top; tools: the tool line (colours, skins, posture, seat); inputbuttons: the buttons beside the input (Enter sends); footer: the status lines under the input |
| panes | When the brain opens a screen for you, one at a time beside the chat, or several? | one; several |
| side | Which side should the pane sit on? | right; left |
| tone | Black, light, or the stock warm dark? | black; light; default: stock |
| face | Serif, mono or sans for the conversation? | serif; mono; sans |
| weight | Thin type or normal? | thin; normal |
| size | Text small, normal or large? | small; normal; large |
| width | Narrow column, wide, or the full width? | narrow; wide; full |
| voice | Voice: off, answers read aloud, or hands-free? | off; speak: read aloud; handsfree: hands-free |
| surfaces | Which ways of working do you want on your home? (several allowed) | chat: chat; decisions: decisions; systems: systems page; talkthrough: talk-through; thoughts: just thoughts; phone: voice notes from the phone; sidepane: side pane views; terminal: terminal |

## The surfaces step (2026-11-13)

The last step, after the look. Name each way of working in one line with what it is for, then let the person pick. The list is `SURFACE_LIST` in `scripts/cc/cc_layout.py`; say these sentences, in the person's language:

| value | what it is for |
|---|---|
| chat | talk one-to-one with your brain; everything else starts from here (always on: the home is the conversation) |
| decisions | one decision after another, each with a yes or a no; a yes starts its work |
| systems | every project as a tile with its own thread beside it, to see all of them at once |
| talkthrough | press record and speak freely for minutes; the brain cuts it into thoughts and files them |
| thoughts | type or say a thought that is filed for later, not answered |
| phone | send a voice note to your brain's messaging bot; it lands on the memo tape and is cut the same way |
| sidepane | threads, board, agents and export open beside the conversation |
| terminal | a plain shell on your box, for the steps only your own hands should run |

- Picking is by press: open the pick-list beside the conversation with `<pane>/layout?step=surfaces</pane>`, where each way of working is a chip with its sentence. Or take the answer in words.
- Defaults by person: the `member` and `org` presets (a newcomer) carry `chat` and `talkthrough`; the `owner` preset carries no answer, which is every surface. Say the default and ask only for changes.
- A surface left out is only not shown on the home and its header; its address and its slash command keep working. Nothing is removed.
- Talk-through is coming, not yet working on a console (2026-11-14): its recorder lives on the memo tape page, a desk page the console serves as a raw file, and since the 2026-11-13 security audit raw pages run sandboxed and cannot send to the bridge. Until the tape becomes a console page of its own, say "coming" when you name it; picking it already puts its button on the home, and the button opens the tape.
- The tape page's place: `CC_PAGE_TAPE` in the bridge's environment when the tape lives elsewhere than in/memos/index.html (for example inside the world's checkout).

## How the answers become the layout

When you have the answers, end one message with exactly one block, using the option values from the table (values, not the words), and only for questions that were answered, with the preset when one was chosen:

```
<layout>{"preset": "owner", "answers": {"first": "talk", "never": ["board", "gallery"], "panes": "one", "side": "right", "tone": "black", "face": "mono", "weight": "thin", "size": "normal", "width": "narrow", "voice": "off", "surfaces": ["chat", "talkthrough", "systems"]}}</layout>
```

- `never` and `surfaces` are lists (`never` empty for none; `surfaces` always holds `chat`, added when left out). Every other answer is a single string.
- `preset` is optional; without it the answers adjust the stock console, as before.
- The bridge turns the preset and the answers into the layout file with `from_answers` (this is the `layout.apply` step) and stores it as a proposal. It does not apply. Say in the same message that the layout is waiting and that the owner presses "apply" on the card (or at /layout).
- A block that does not validate is refused with the reason, shown to the owner. Do not retry with invented keys.
- After applying, the owner can change any answer later at /layout (the same chips), or press "save layout" in the console footer to store how the console looks right now.

## What the answers change

| answer | effect in the console |
|---|---|
| first | the page the console opens on: the conversation, /gallery or /panes (once per browser session); doors opens a blank thread with a few large doors by activity, generated from the persona and the installed apps (scripts/cc/cc_doors.py; amended 2026-11-08); today opens the conversation with the Today app beside it (layout key `start`: `/apps/<id>` or /tasks, /files, /graph, /guide; amended 2026-11-04); week opens it with the Week app beside it (start = `/apps/week`, the owner's week page; amended 2026-11-10; the app installs from /apps, "Shipped with this brain") |
| never | the named block is hidden; "reset layout" and /layout bring it back |
| never: nav | the top row (threads, new thread, side by side, gallery, board, agents, export) is hidden; the "everything" drawer stays, and /new, /help and the other slash commands still work (2026-11-06) |
| never: tools | the tool line (colour wheel, tint, text, skins, wallpaper, posture, seat, learn) is hidden; /posture and /seat still work |
| never: inputbuttons | attach, talk, send now and send leave the input: Enter sends, files attach by drop or paste, voice runs hands-free (/talk free), Esc stops; a stop button shows only while an answer runs; the four asks above the input (read the threads, where were we?, help decide, just thoughts) go too, and stay as typed words (amended 2026-11-12) |
| never: footer | the status lines fold into one "···" link that unfolds them; a disk over 95% full, documents waiting for approval and cards waiting for a decision still show as one line; the idle line above the input shows only while an answer runs (amended 2026-11-12) |
| panes: one | hides the "side by side" button |
| side | the pane opens left or right of the conversation |
| tone | colour preset: black, light, or the stock palette |
| face | serif is Lora, mono is JetBrains Mono, sans is the system sans |
| weight, size | thin type (font weight 300); text zoom 0.92, 1, 1.12 |
| width | the conversation column: 860px, 1180px, or the full width |
| voice | answers read aloud on or off; hands-free on or off |
| surfaces | layout key `surfaces` (a list, or null for every surface). The home and its header show only the picked ones: decisions, systems page, talk-through and tape buttons in the header, the "just thoughts" button above the input, the phone strip (a new thread from the messaging bot), the threads, board, agents and export buttons, the terminal button. Decisions, talk-through and the tape show only when this brain has their page (the bridge's `pages`: `CC_PAGE_DECISIONS`, `CC_PAGE_TAPE`, or the desk defaults out/decisions/index.html and in/memos/index.html). /layout shows and edits the same list (2026-11-13) |

Accent and the other colour variables are not asked; the owner sets them at /layout from a short list.
