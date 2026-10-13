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

## What is next

- **The map as the scenery layer.** One surface where people, boxes and modules are nodes and each node is a button:
  - Pressing a person opens their thread or brain.
  - Pressing a box opens its System view and jobs.
  - Pressing a module opens its repo in Files or its pane.

  `/boxmap` (bridge) and `/graph` (memory) are the two existing seeds. The map should read the registry (systems, nodes) rather than keep its own list. Choices then become edges you can press: an `agent` choice draws a new node hanging off the thread that spawned it.
- Sub-threads with a parent: the bridge does not yet record which thread an `agent` choice came from. A `parent` field on the thread record would let the map and the thread list nest them.
- Choices on other surfaces: Telegram (`_tg_send`) likely gets the block as raw text. This is read from the code, not tested. It should strip the block or offer it as inline buttons.
- More chips, only when one earns its place: job ids (open the job tile) and commit hashes (open the log).
