# Campaign day: many jobs at once, one folder at the end

Created 2026-10-27. Code: scripts/cc/cc_campaign.py (the `cc-job campaign` verbs), templates/campaign/. Tests: tests/test_cc_campaign.py.

## What it is

A campaign day is one sitting of parallel work by the brain's reasoner: several jobs run at the same time, each in its own lane, and each ends with a report in one shared folder.
The owner says what the day is for and how much it may spend, then leaves.
At the end there is one folder to open: one report per lane, and a scoring pass that has checked every claim on the box and ends with the single list of what waits on the owner.

It is built from what one owner ran on 2026-10-27: a charter, about twenty jobs in two waves, a measuring lane that pre-registered predictions in the morning and scored them in the evening.
The parts that worked are the kit: the charter every job reads first, lanes that own paths, the same four-part report from every lane, a measurement written before the work and checked after it.

Pieces:
- The charter (CHARTER.md): the goal, the owner's words, what is off limits, the money caps the owner fills, the rules every job follows, and the lane table.
- One brief per job (briefs/<name>.md): first line `Your lane: <LANE>, job <JOB>.`, second line `Owns: <path> ; <path>`, optional `Cap:` (this job's reasoner spend cap) and `Share:` (its outside-spend share), then the work in steps. Files starting with `_` are notes, never launched.
- The report contract (REPORT-CONTRACT.md): every lane writes reports/<LANE>.md with four sections: Done; Verified, and how; Not verified; Needs the owner (minutes each, and the one word or click that settles it).
- The pre-registration (briefs/preregister.md, job PREREG-1): before the work, the measuring lane writes the question, the measures, numbered predictions with probabilities and the scoring rule into card.md, and takes a baseline.
- The scoring pass (job SCORE-1, started by `close`): every claim in every report checked on the box and marked verified, unverified or false; the predictions resolved and scored; reports/SCORE.md ending with one list of what waits on the owner.

Everything lives in one folder on the desk: `~/out/campaigns/<date>_<name>/` (CHARTER.md, REPORT-CONTRACT.md, briefs/, reports/, templates/, spend.tsv, launched/, campaign.json).

## Run one in five commands

```
cc-job campaign new "music library"       # the folder; then fill the goal and the caps in CHARTER.md and write the briefs
cc-job campaign lanes --write             # the lane table from the briefs, into the charter; overlaps are named
cc-job campaign launch --only PREREG-1    # the pre-registration first; then `cc-job campaign launch` for the rest
cc-job campaign status                    # per lane: running, done or failed; report present; minutes owed
cc-job campaign close --in 30m            # schedules the scoring pass; no launch after it
```

In practice the owner says the goal in a conversation and the reasoner does the five commands: it writes the briefs from the conversation, shows the lane table, and launches when the owner has filled the caps.
`--campaign <name or folder>` picks a campaign; without it, the newest one still open. `close --at 18:30` uses the box clock.
Each launched job is an ordinary cc-job: a tile on the board, its log in ~/out/jobs/, its prompt and output in the campaign's launched/ folder. `launch` again starts only the briefs not started yet, so a second wave is: write the new briefs, `lanes --write`, `launch`.

## Safety rails

- Lanes own paths. A job edits only the paths on its brief's Owns: line; anything else becomes a next step in its report. `launch` refuses while two lanes own the same path or one inside the other, and while a brief has no filled lane line or no Owns: line.
- Claims. If the world has a claims tool (who is editing where, right now), each job claims its paths before editing; otherwise the Owns: line is the claim. The scoring pass checks git log by path for edits outside a lane.
- No publish, no send. No upload, deploy, DNS change, post or message to a person. A job prepares the thing so the owner's yes is one word or one click.
- No delete on drives, servers or volumes; copies are additive and checksummed. No .env, secrets or credentials; no sudo (jobs never run sudo anyway).
- No push unless the charter says so for that repo; history is never rewritten (no rebase, reset --hard or stash in a shared checkout).
- Caps. `launch` refuses until the owner has filled the money fields in the charter. The per-job cap goes to the reasoner as its spend limit; a brief's `Cap:` overrides it for that job. Outside spend (rented compute, paid generation, storage) is written to spend.tsv before it happens and checked against the campaign cap and the lane's share; over a cap, the job stops that step and writes the ask in its report. Rented compute ends before the job ends.
- The kill switch holds: while `cc-job halt` is set, `launch` and `close` start nothing (docs/KILL_SWITCH.md). Every job command also passes the bridge's job guard, so a campaign job keeps the turn's permission posture.

## Roles and the Lab

A campaign is work the brain does for the owner on one day; a role is how a person enters the brain (a bundle of brain-apps and a home layout picked at first use). They meet in two places, where the brain has them:
- A lane can be named after a role ("The Scientist" lane, "The Producer" lane): its brief installs nothing, but its Owns: paths and its report follow the role's apps, so the owner reads the result where that role works.
- The measuring lane's card.md is the five-field experiment card (question, prediction, method, result, critique). An experiment-viewer brain-app (a Lab), if installed, can show it with the predictions as guess-then-reveal; its share view must strip private paths before anything leaves the box.
Neither is required: a campaign runs on cc-job and the desk alone.

## What it does not do

It does not write the briefs by itself, pick the caps, publish, push, or decide what the owner should look at first beyond the scoring pass's list. It does not run a second wave on its own. The scoring pass is a reasoner of the same family as the lanes it scores; its judgements are listed so the owner can overrule them.
