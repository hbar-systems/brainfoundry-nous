---
title: "Part 4: Memory and privacy"
date: 2026-10-18
---

# Part 4: Memory and privacy

## What is remembered

Documents you upload on the Knowledge tab, cut into small pieces the brain can search.
Your conversations, saved in the brain's chat record.
Your persona: who you are and how you want answers.
Some things are only proposed to memory (for example by a tool, or from a conversation); they wait on the Knowledge tab until you approve them.
Uploads that look like hidden instructions are held in quarantine until you look at them.

## Open, local-only, and the vault

Every piece of memory is open or local-only.
Open (the default): any model the brain uses may read it, on your server or at a provider.
Local-only: only a model running on your own hardware, answering you in the console.
Choose with the Privacy chips on the Knowledge tab, before an upload or per document afterwards.
Once a local model has read local-only memory in a session, a hosted model may not continue that session; you are offered a fresh one.
For the most private files there is the vault: a folder on the server that only you can read, not even the reasoners.

## Public and private

Nothing is public unless you make it so.
Only memory you deliberately mark public is shown to visitors of your brain's public page or to other brains.
Everything else stays between you and the models you use.

## Who reads what

You read everything, in the console.
A hosted model reads open memory, and what it reads is sent to its company (for example Anthropic or OpenAI).
The reasoners in the conversation can read the files on the server that their user can read, but not the brain's secrets file and not the vault.
Brain-apps read only what you approved at install.
Anyone with the brain's API key, and anyone with administrator rights on the server, can read everything.
Memory is not encrypted on disk, and backups hold everything.

## Export

Settings, Export, "Export my brain", then Download.
You get one file with your memory, conversations, persona, installed apps and friends.
Passwords and keys are deliberately left out, so the file is safe to store, but it still holds all your memory: keep it as carefully as the server.
It can be restored onto any brain.

## Backup

Backups are copies kept on the server, made by a script the owner of the server schedules.
Ask whoever runs your server whether backups are on and where they go.
A backup on the same server does not survive the loss of that server; keep an export somewhere else too.

More: [privacy and memory](../public/06-privacy-and-memory.md), [who reads what](../public/07-who-reads-what.md), [export](../EXPORT.md), [backup and restore](../BACKUP_RESTORE.md), [import](../IMPORT.md).
