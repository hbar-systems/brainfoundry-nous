# The world of {{PERSON}}

Created: {{DATE}} (opened by init-world.sh from templates/world, interview v{{INTERVIEW_VERSION}}).

This folder is the operating system of one brain: the rules, the state, and the filed work of one person.
The brain engine updates itself; this folder is never touched by an update.
It is a git repository; everything in it is yours.

## Read order

Before doing anything substantive, read in this order:

1. ME.md: who the person is and how they want answers.
2. NOW.md: the current state (focus, open, next). Keep it current.
3. The README.md of the area the work belongs to (areas/<area>/README.md).

Then decisions.md if a rule seems to be missing, and ideas.md before proposing something new.

## Hard lines

- Never push this repository anywhere unless the person says so in this conversation.
- Never read or print `.env` files, tokens, keys or passwords, here or on the box.
- Never take in anything the person has fenced off (see "What stays outside" below), even if it would help.
- Never delete or rewrite history in this repository; corrections are new lines, new commits.
- Never spend money without a yes in the conversation.
- Commit by exact path (`git add <path>`), never `git add -A` or `git add .`.

## What the brain may do (from the interview, question A8)

Each row is one of: allowed, ask me first, never. Change a row only when the person says so, and log it in decisions.md.

| Action | Setting |
|---|---|
| Read my messages | {{PERM_read}} |
| Write messages for me | {{PERM_write}} |
| Send messages for me | {{PERM_send}} |
| See my calendar | {{PERM_cal_see}} |
| Change my calendar | {{PERM_cal_change}} |
| Look things up on the web | {{PERM_web}} |
| Remember everything I tell it | {{PERM_remember}} |
| Spend money | {{PERM_spend}} |
| Post in public | {{PERM_post}} |
| Anything else | {{PERM_else}} |

"Ask me first" means: show the exact action as a card and wait for the answer. No answer is a no.

## What stays outside

Things the person said they would never tell an AI (A9), and tools or material that must stay out (B17):

- Never tell: {{NEVER_TELL}}
- Stays outside: {{FENCE}}

Nothing on this list is imported, read, summarised or remembered. If it arrives anyway (an attachment, a pasted message), say so and do not use it.

## Filing rule: the desk and the archive

- The desk is outside this folder: `~/in/<date>/` (what the person gave) and `~/out/<date>/` (what you made). The desk is not the archive.
- "File this" means: move the item from the desk into this folder where it belongs, then commit by exact path, then say in one line where it went.
- Text is committed at its place: an area's `notes/` as a dated note, or decisions.md, ideas.md, NOW.md.
- Binaries (audio, video, large PDFs, images) are not committed. They go under `library/<yyyy-mm-dd>_<source>/` (gitignored) with one row in `library/MANIFEST.md`, which is committed.
- When the place is not clear, ask with two options.

## Each session

- Start by reading ME.md and NOW.md.
- End by updating NOW.md and, if anything was decided or filed, writing a note from journal/TEMPLATE.md into the area's `notes/` folder.
- A new rule or a changed row above is one appended line in decisions.md.
- An idea that is not built now goes to ideas.md (ten slots per area; a full area means one goes out first).
