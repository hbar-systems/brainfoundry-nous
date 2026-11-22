---
created: {{date}}
campaign: {{name}}
kind: campaign charter (cc-job campaign new, templates/campaign/CHARTER.md)
status: draft; the owner fills every <...> field before `cc-job campaign launch`
---

# Campaign {{name}}, {{date}}: <one-line goal>

A campaign is one day (or one sitting) of parallel jobs, each in its own lane, each ending with a report in one folder.
This file is the charter: every job reads it first. The owner writes the goal, the money caps and anything off limits; the reasoner writes the briefs and the lane table.

Folder: {{dir}}
Briefs: {{briefs}} (one file per job; `_`-prefixed files are never launched)
Reports: {{reports}} (one file per lane, the contract in {{contract}})

## The owner's words

- Launch: "<the words that started the campaign, quoted>"
- Goal: <what the owner wants to see at the end>
- Off limits: <repos, folders, people, services no job touches>
- Standing gates lifted for this campaign only, and when they come back: <none, or which>

## Money caps (the owner fills these; a job stops at a cap and asks)

| cap | value |
|---|---|
| per job, reasoner spend (a `Cap:` line in a brief overrides it for that job) | <n> |
| whole campaign, outside spend (rented compute, paid generation, storage) | <n> |
| per lane, outside spend | in the lane table below; a lane without a number has 0 |

Outside spend is logged before it happens: one line in {{dir}}/spend.tsv (time, lane, item, estimate). Before a paid call a job adds its line and checks the column sum stays under the campaign cap and under its lane's share. Over: it stops that step and writes the ask in its report. Rented compute ends before the job ends; nothing is left running.

## Rules every job follows

1. Read this charter, then the world's CLAUDE.md. Your lane owns only the paths in the table. Anything outside it is written down as a next step in your report, not edited.
2. If the world has a claims tool, claim your paths before editing and release them at the end; otherwise the Owns: line of your brief is your claim.
3. Before editing a repo, bring it up to date without rewriting history (fast-forward or a plain merge; never rebase, reset --hard or stash). Commit by exact path. Never push unless the owner wrote "push" for that repo in this charter.
4. Never publish or send: no upload, deploy, DNS change, post, or message to a person. Prepare it so the owner's yes is one word or one click. Local preview builds are fine.
5. Never delete anything on a drive, server or volume. Copies are additive and checksummed.
6. Never touch .env files, secrets or credentials. No sudo.
7. Money: the caps above. A job never raises its own cap.
8. Report to {{reports}}/<LANE>.md following {{contract}}: done, verified and how, not verified, needs the owner (minutes each). Every claim names something the scorer can check: a path, a commit hash, a command and its output, a link.
9. Plain words. Name what you did not do.

## Lanes

Generated from the briefs by `cc-job campaign lanes --write` (their Owns:, Cap: and Share: lines); edit the briefs, not this table. Two lanes owning the same path, or one inside the other, stop the launch until a brief is changed.

<!-- lanes:start -->
(no briefs yet)
<!-- lanes:end -->

## Measurement

Pre-registration (before the work): {{briefs}}/preregister.md, from {{dir}}/templates/PREREGISTER.md; launch it first with `cc-job campaign launch --only PREREG-1`.
Scoring pass (after the work): `cc-job campaign close` starts {{dir}}/templates/SCORE.md (or {{briefs}}/_score.md when the reasoner wrote one); it writes {{reports}}/SCORE.md and ends with the one list of what waits on the owner.
