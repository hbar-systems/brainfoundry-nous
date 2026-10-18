---
title: "Part 3: Workers"
date: 2026-10-18
---

# Part 3: Workers

Your brain can do work in three ways besides answering you.
All three run on your server, as a plain user without administrator rights.

## Helpers inside an answer

During one answer the reasoner may hand pieces of the work to helpers that run side by side.
They end when the answer ends.
Their actions pass the same cards as the reasoner's own; the Board counts them.

## One-off jobs

A job is a command that keeps running after the answer is finished, like a long download or a render.
The reasoner starts it when you ask for something that takes minutes.
It shows as a tile on the Board, and a small card appears in the conversation that started it when it is done.
Starting a job is itself a command, so it asks you (a card) unless your posture lets it run.
Once started, a job does not stop to ask again, and it never runs with administrator rights.

## Standing agents

An agent is a worker you create on the Agents page that runs on its own schedule.
You give it a name, a mission in a sentence, the folders it may write in (its ground), a schedule (on call, or every 15 minutes up to weekly), a budget per run (0.5 to 20 USD; the run stops at its budget), and optionally a model.
At most three agents start in the same minute.
Each run ends with a short report, a sitrep, shown on the page.
You can pause, resume, run now, or retire it; a retired agent's file is kept, not deleted.

Each agent has an autonomy level, and only you can set it:

- 0 propose: it writes only its report; every change is a suggestion to you.
- 1 branch (the default): it saves its work on its own branch and never publishes it.
- 2 ship: it may also publish its own branch onto the main line of its repository, only after the tests pass; the page asks you to confirm this level.

## What runs alone, and what asks

| | Runs without asking | Asks you | Always refused |
|---|---|---|---|
| You, in a conversation (posture "cards") | reading | every edit and command | reading secrets files |
| You, posture "auto" | ordinary edits and commands | anything with administrator rights; every write to a connected app | |
| You, posture "judged" | actions a small judge model scores as harmless and on-request | the rest; administrator rights; connected-app writes | |
| A standing agent | reading, edits inside its ground, saving its work, tests, a fixed list of checking commands | administrator rights | publishing (except level 2's own branch), force-publishing, deleting branches, `rm -rf`, secrets files, web requests that send data |

Choose your posture by typing `/posture` in the conversation.
"judged" needs a judge key on the server; when the judge cannot answer, it asks you.
On any card you can tick "don't ask again" for that kind of action; the list under the conversation has an "ask again" link for each.
Dangerous kinds (deleting, administrator rights) never offer the tick.

An agent runs while nobody is watching.
So in practice, anything outside its allowed list is not run: the agent writes "(not checkable)" or a proposal in its sitrep, and you decide.
If your posture is "auto", agents use it too, and the classifier may let more through.

## The permission file

One file widens what every agent may do: `permissions.json` in the agents folder on your server (`~/agents/` of the user the reasoner runs as).

```
{"bash_allow": ["make build"], "tools": ["WebSearch"], "read_dirs": ["/srv/shared"]}
```

`bash_allow` adds commands, `tools` may add WebFetch or WebSearch, `read_dirs` adds folders agents may read (never write).
Administrator commands in it are dropped, and the refused list above always wins.

More: [the CC guide](../CC.md), sections "Hands on the box", "Files, jobs and attachments" and "Standing agents".
