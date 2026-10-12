# The world template: the operating system of a new brain

Created: 2026-10-12.

A brain box has three layers. The first two are the engine and its owner state; the third is the person's world, a plain folder of markdown that holds their rules, their current state and their filed work. The engine ships a template of that folder at `templates/world/`, and `scripts/cc/init-world.sh` opens it once per box.

## The three layers

| Layer | Where on the box | Who changes it | Touched by Update? |
|---|---|---|---|
| Engine | the brainfoundry-nous checkout | the Update tab, the same for every brain | yes |
| Owner state, not in git | `api/brain_persona.local.md`, `.env`, the bridge's state files | the console, the operator | no |
| The world | `/home/<hands-user>/world`, its own git repository, with the desk `~/in` and `~/out` beside it | the person and their reasoner | never |

Update refreshes `templates/world/` inside the engine. The world that was opened from it is a separate repository and is never overwritten; a later change to the template reaches a person only as a proposal they can accept.

## What is in the folder

```
world/
  CLAUDE.md          rules: read order, hard lines, the permission grid (interview A8), what stays outside (A9, B17), the filing rule
  ME.md              who the person is, what the brain is for, how they want answers, look and feel
  NOW.md             current state: focus, open, next, expectations (the reasoner keeps it)
  DEVICES.md         every device and storage place, joined or not (interview block 3)
  APPS.md            what is plugged in and why, one row per app
  decisions.md       append-only, D-numbered; D1 is "brain opened <date>"
  ideas.md           parking, ten slots per area
  areas/README.md    one folder per thing the brain is for; init-world.sh makes the first one (areas/<area>/README.md, notes/)
  library/MANIFEST.md   one row per import: date, source, size, kinds, folder, the yes
  journal/TEMPLATE.md   the five-line session note
  .gitignore         library originals, secrets, OS junk
```

Eleven items ship; nothing else. People, repositories, a registry: added on demand by the reasoner, with a line in decisions.md. The desk (`~/in/<date>/`, `~/out/<date>/`) is outside the world; "file this" moves a desk item into the world and commits it.

Every file starts with a creation date and a few lines of plain guidance. Placeholders are written `{{KEY}}`; init-world.sh replaces each with the interview answer, or with `(fill in)` when there is none.

## How init-world.sh runs

```
bash scripts/cc/init-world.sh [--target DIR] [--answers FILE] [--owner USER] [--persona-out PATH] [--wire]
```

1. Refuses if the target already holds a `.git` or any file: a world is opened once and never clobbered. Rerunning prints "already open" and exits 0.
2. Copies `templates/world/` to the target (`$CC_WORLD_DIR`, else `/home/${CC_HANDS_USER:-hands}/world`).
3. Fills the placeholders from `--answers`, the interview form's "Save as JSON" export (`person`, `date`, `version`, `answers{A1..D13, A8_<perm>, B12_*, ...}`, `devices[]`, `oldDevices[]`, `storage[]`). The first area comes from B1 (their own mind: `mind`; a teacher: `study`; a health guide: `health`; a private counsellor: `counsel`; a character: `character`; the memory of someone: `memory`; other: the words given; none: `general`), with `inbox` added when B7 names mail.
4. With `--persona-out`, writes the brain's persona file once from ME.md's one line (on a box: `api/brain_persona.local.md`), on top of the engine's persona template. After that the console owns the persona and ME.md owns the reasoner's view; drift between them is known and not solved here.
5. `git init` on `main`, every file added by exact path, one first commit `world: opened <date>` with the person's name (`--git-name`, `--git-email` to override).
6. With `--owner`, run as root: chowns the world to the hands user with the group modes the bridge needs. With `--wire`: sets `CC_WORLD_DIR` and `CC_WORK_DIR` to the target in the bridge env (the laptop's shape, docs/CC.md) and restarts cc-bridge.
7. Prints the tree and the D1 line, for the operator to read back to the person.

Where it is called: `scripts/cc/split-hands.sh` step 2, when `CC_INIT_WORLD=1` is in the environment and the hands have no world yet (`CC_WORLD_ANSWERS=<file>` passes the answers). The later steps of split-hands then point the bridge at it and restart. On a box that is already split, run the script by hand with `--owner hands --wire`.

## How to customise

- Change the text for every new brain: edit `templates/world/*` in the engine and commit; the next Update carries it. Keep the eleven items and the `{{KEY}}` names (the test `tests/test_init_world.py` checks both).
- Change one person's world: edit the files in their world and commit there; the template is not involved.
- Another template folder for a kind of brain (an organisation, a showroom): keep it anywhere and pass `--template DIR`.
- The template must stay free of the operator's own names, private state and any business logic; it is governance and plain words, shipped under the engine's licence.
