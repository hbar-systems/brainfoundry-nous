---
created: 2026-11-27
job: STEWARD-1
---

# The setup period: a helper finishes the move-in

A member's move-in took four days of the operator at her laptop, reading photos of her screen into a thread: the import stalled, three counts disagreed, a queue was lost on restart, a re-run brought 95 files twice, and her own brain told her to run another import line with a token, because it could not see what it already held. The setup period replaces that relay. A helper (the operator's steward run, outside this template) does the setup through the brain's own doors, under a key the member agreed to, and stops at the steps only a person can do.

## What the person does, and only that

1. **The line.** On the home's move-in card they press "Copy, and let the helper finish". The consent sentence sits right above that button, and "Without the helper" copies the line alone. They paste the line on their computer.
2. **Their choice.** "Bring these" on the computer's list.
3. **Their seat.** Sign in their own Claude or ChatGPT.
4. **Their map.** "Looks right", once the map card exists on their brain (ORGANISE-1).

Their screen never shows a token, a command (apart from the one line, which is the move-in's own) or a file path.

## The key

- **Minted** by the member's press (`POST /setup/key` through their console, which holds the owner key). The body carries the sha of the consent line they were shown. A stale or missing line is refused.
- **Lives** 48 hours by default and 72 at most. It ends earlier on their Done press (`/setup`), on handover, or on `POST /setup/revoke`.
- **Never shown, never returned.** The api writes the raw key once to `<runtime>/setup/steward.key` (mode 600). The operator's steward collects it as root on the box, the same trust the ready check already has. Only a sha256 is kept; it is checked in constant time.
- **Scopes**, and nothing else:
  - `state`: counts, never titles or text.
  - `duplicates`: rejects pending copies of what is already held. It never deletes a stored document. A rejected proposal keeps its text, so a wrong call is undone by proposing it again.
  - `approve`: reads in what the person chose. That is their "Remember all", or the files of the computer run whose list they chose, including that run's AI-history chats. Files the safety scan held stay for their one-by-one look.
  - `ask`: one test question through the console's chat door.
  - `log`.

  No persona, layout, setting, key, export, Update or password route answers to it.

## The consent line (en; de and ru in api/setup_steward.py CONSENT)

> Let the setup helper finish moving you in, until {date}. It sees counts, never your files or chats. It clears copies that came twice, reads in what you chose, and asks your brain a few test questions. It cannot change your words, see your passwords or delete what you kept. It stops on {date}, or when you press Done.

## The doors

| route | who | what |
|---|---|---|
| GET /setup/consent?lang= | owner (console) | the line, its sha, the end date |
| POST /setup/key | owner (console) | the member's yes; mints the key into the runtime file |
| GET /setup/status | owner | open or not, until when, the last action, the steward's last action |
| POST /setup/revoke | owner | ends the period (the member's Done, or handover) |
| POST /setup/handover/password | owner (console, the guided screen) | the member's new console password, kept as a bcrypt hash only |
| POST /setup/key/check | owner (the bridge) | is this setup key good for this scope |
| POST /setup/log/append | owner (the bridge) | the steward's test turns, logged in one place |
| GET /setup/state | setup key | health facts, counts by source, waiting, reading, copies, chosen, held, refused |
| POST /setup/duplicates/clear | setup key | rejects the copies (`dry_run` to count only) |
| POST /setup/approve | setup key | starts reading what the person chose, at the brain's pace |
| GET /setup/log | setup key | the last 50 actions |
| bridge GET /setup/state | setup key (checked by the api) | seat signed in, console language, start page, layout, persona chars, turns |
| bridge POST /setup/ask | setup key (checked by the api) | one question through the member's own chat door, in its own thread labelled "Setup check"; a verdict comes back (answered, drew on N of theirs, expected words used, setup advice given, "nothing is here" said), never the text |

## What copies are

Copies are worked out on the brain, in `duplicates()`:

1. A pending file whose name is already held, and whose text starts the way the held one does (its first 400 characters), is a copy. The same name with a different start is a newer version, left for the person.
2. Two pending items with the same text are copies of each other. The shortest path stays.

## The member's reasoner during the period

While a period is open, every console turn carries a `<setup-period>` line in the person's language (scripts/cc/cc_steward.py NOTE). For setup questions it says: no commands, tokens, paths or import lines, and no list of setup steps. It says to search Knowledge first, then say plainly what is in, that the rest is being handled, and that their page (`/setup`) shows any step that is theirs. It sits beside KNOWLEDGE-REACH-1's line ("search Knowledge with cc-job recall before saying something is missing") and does not repeat it. The status is asked from the api at most once a minute.

## Handover

1. The member picks a new console password on `/setup` ("Choose your password", typed twice). The api hashes it and keeps only the hash, mode 600.
2. The operator presses, on the box: `sudo bash scripts/setup-handover.sh <handle>` (a dry run first, then `--apply`). The script:
   - swaps exactly one basicauth line in the member's console block;
   - validates and restarts Caddy;
   - ends the setup key;
   - removes the kept hash;
   - prints the steward's last action.

   Undo: put the backup it names back and restart Caddy.

The member never tells anyone the password. The operator never sees it.

## What it cannot do (by design)

- It cannot read a document, a title or a chat. The steward gets counts and verdicts.
- It cannot change persona, layout, keys or settings. Those stay operator steps, and the steward names the template file that fixes them for every brain.
- It cannot delete anything stored, run Update, or end its own period early on the member's behalf.
- It cannot work after its end time, or after Done.
