# The visual layer

Created 2026-10-13.

The chat stays the conversation; the visual layer sits above it and turns what the reasoner says into things you press. This is the first real step. hbar's words: "make it a button and you send out an agent", "the actual thing to read, always able to go full screen", "the chats are turned into visual-interactive, a layer above".

## What shipped (2026-10-13)

### Choices

The reasoner may end an answer with one block:

```
<choices>[{"label": "Ship it", "send": "Commit and log it", "mode": "reply"},
          {"label": "Audit first", "send": "Audit the diff in ops/ for leaks", "mode": "agent"}]</choices>
```

- `label`: the button text (max 80 characters).
- `send`: what the button sends. If it is missing, the label is sent.
- `mode`:
  - `reply` (the default) sends `send` as the next message in this thread.
  - `agent` starts `send` as a new thread of its own, through the bridge's `/cc/chat` with `new: true`. That thread runs beside this one and shows in the thread list. The page stays on the current thread and adds a note that the other thread started.
- At most 4 choices; anything past 4 is dropped. The bridge's system prompt says: offer 2 to 4 choices when the answer ends in a decision, never more.
- The page cuts the block out of the text before rendering it (`ui/lib/choices.js`, `splitChoices`). While the answer is still streaming, an opened block that has not closed yet is hidden, so raw JSON never shows. A block that does not parse shows no buttons.
- Voice never reads the block aloud (`_SPEAK_PANE` in `scripts/cc/cc-bridge.py`).
- Once one button is pressed, all the buttons in that answer are disabled. That state lives only in the page; a reload brings the buttons back.

### Highlights

- Paths on the box were already links that open the Files pane. They are now drawn as chips.
- Amounts with a currency are drawn as gold chips (`remarkMoney`). Examples: EUR 34, 34 EUR, €27-31, $0.39, 1,200 USD, £5. Dates and version numbers are left alone.
- Neither kind of chip applies inside code or links.

### Full screen

- Every pane has a "full screen" button that covers the whole console. Escape returns. A page inside the pane passes its Escape up with `postMessage({type: 'cc-pane-esc'})`.
- Every file view in Files has a "full screen" button:
  - Hand-made visuals (html, and the `.view.html` beside an md) go full screen alone, as before.
  - Everything else, including auto-rendered markdown, goes full screen with its toolbar. The body sits in a centred column up to 1100 px wide.
  - Escape leaves the file's full screen first, then the pane's.
- Bug fix from hbar's screenshot of 2026-10-13: in a narrow pane, the file title was squeezed to one letter per line and pushed the body out of sight.
  - The title now wraps as a whole, with a 220 px basis.
  - Under 760 px, the open file takes the whole pane, and a "list" link goes back to the list.

## The tool line (2026-10-13)

hbar: "a small line where tools are represented, and those tools can in real time change the brain's look, not via GitHub pushes; and a circular colour wheel so the person can tweak the look of different conversations live".

- A slim strip above the conversation, folded to one line ("tools ▸" with a dot in the current accent). Open or folded is remembered in the browser (`cc.toolline`).
- Open, it holds:
  - A colour wheel, drawn by the page (no browser colour input): hue round the circle, strength from the centre out. It sets this conversation's accent (`--accent` on the conversation, so chips, links and cards follow).
  - Tint 0, 6, 12, 20: how much of the accent washes the conversation's background. "reset" goes back to the skin's own accent.
  - Text 14, 16, 18 and compact or comfortable, for this conversation. The footer links still set the default for conversations without their own.
  - The nine skins (gold, paper, sapphire, forest, crimson, mono, fox, octopus, owl) as chips. A skin chosen here applies while this conversation is open; tapping it again goes back to the console skin (Settings, `bf-theme`).
  - Posture (cards, auto, judged), only where the box lane is on. Posture is the box's, not the thread's: it applies to every conversation from the next turn, as `/posture` does.
- Where it is kept: on the box, in the thread record (`~/.cc-bridge/threads.json`), field `style`, through `POST /cc/threads/update {brain, style}`. The bridge keeps only known keys with checked values (`_thread_style`: accent `#rrggbb`, tint 0 to 30, text, density, skin, learn); `style: {}` clears it. The page writes half a second after the last touch, so a drag round the wheel is one write. Another device opening the same thread gets the same look.
- A new conversation that has no thread id yet keeps its look in the page only, until its first answer; then the next touch saves it.
- Nothing here needs a push or a rebuild: it is data on the box, read by the page.

## Learning mode (2026-10-13)

hbar: "a system of learning cards: if something is technical, behind the card a mini lesson, learning mode; copy a bit the interview pack's recall, but improvising off whatever the AI's response is in any conversation".

- "learn off / on" is a chip on the tool line. It is part of the thread's look (`style.learn`), so it is per conversation and kept on the box.
- When it is on, every bold phrase and every short inline-code term in an answer carries a small "learn" door.
- Pressing the door opens a lesson card. The bridge makes the lesson on demand from the term and the paragraph around it (`POST /cc/learn {term, context}`).
  - The card asks a guess-first question (the estimate-question rule): type a guess or skip, then "reveal".
  - Then it shows the answer (two to four sentences) and one example, with "save to deck" and "go deeper". "go deeper" asks in the thread.
- How the lesson is made: one side call to the reasoner CLI (`claude -p`) on the small model (`CC_LEARN_MODEL`, default `haiku`). The call has no tools, no MCP servers, no memory and no session to resume, and runs in an empty directory (`~/.cc-bridge/learn`). Nothing is posted into any thread.
  - The brain api's `/chat/completions` was not used: it requires a NodeOS loop permit per call.
  - Cost: on a subscription sign-in it draws on the plan, with no per-call charge. On an API key it is a few thousand input tokens (the CLI's own system prompt) plus about 200 output on Haiku 4.5, measured on 2026-10-14 at USD 0.015 per lesson (3.8 s, mostly the cached CLI system prompt). The bridge log prints the CLI's `total_cost_usd` per lesson as `learn: ... cost_usd=...`, so the real number is in `journalctl` after the first use.
- The deck: `POST /cc/learn/save` appends one line to `<world>/learning/deck.tsv`. Columns: date, term, question, answer (with the example), source_thread. The file is created with its header on the first save.
- Recall: the "recall N" chip on the tool line shows the cards due today (`GET /cc/learn/due`), one at a time: reveal, then "got it" or "again".
  - Each answer is one line in `<world>/learning/reviews.tsv` (date, term, ok or again).
  - A card is due 1, 3, 7, then 21 days after its last recall (or after it was saved), stepping on each "got it" in a row. "again" starts it over at 1 day.
  - The chip shows only once the deck has at least one card.
- Needs `CC_WORLD_DIR` on the bridge (the deck lives in the world folder). Without it, saving says so and nothing is written.
- The deck is a plain file in the world. It is not committed by the bridge; world-keep or a thread commits it like any other file.

## What is next

- **The map as the scenery layer.** One surface where people, boxes and modules are nodes and each node is a button:
  - Pressing a person opens their thread or brain.
  - Pressing a box opens its System view and jobs.
  - Pressing a module opens its repo in Files or its pane.

  `/boxmap` (bridge) and `/graph` (memory) are the two existing seeds. The map should read the registry (systems, nodes) rather than keep its own list. Choices then become edges you can press: an `agent` choice draws a new node hanging off the thread that spawned it.
- Sub-threads with a parent: the bridge does not yet record which thread an `agent` choice came from. A `parent` field on the thread record would let the map and the thread list nest them.
- Choices on other surfaces: Telegram (`_tg_send`) likely gets the block as raw text. This is read from the code, not tested. It should strip the block or offer it as inline buttons.
- More chips, only when one earns its place: job ids (open the job tile) and commit hashes (open the log).
