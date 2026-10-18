---
title: "Part 8: Under the hood"
date: 2026-10-18
---

# Part 8: Under the hood

The technical documents, for when you or someone helping you wants the detail.

## What a brain is

- [What is brainfoundry](../public/01-what-is-brainfoundry.md)
- [What is a brain](../public/02-what-is-a-brain.md)
- [Architecture](../architecture.md)
- [Memory architecture](../brainfoundry/memory-architecture.md)

## The conversation and its hands

- [CC: the conversation, cards, postures, jobs, agents, Telegram](../CC.md)
- [Integrations](../INTEGRATIONS.md)
- [Governance and permits](../public/03-governance-and-permits.md)
- [Kernel governance](../brainfoundry/kernel-governance.md)

## Privacy and memory

- [Privacy and memory](../public/06-privacy-and-memory.md)
- [Who reads what](../public/07-who-reads-what.md)
- [Export](../EXPORT.md), [Import](../IMPORT.md), [Backup and restore](../BACKUP_RESTORE.md)

## Other brains

- [Federation](../public/04-federation.md)
- [Federation protocol](../brainfoundry/federation-protocol.md)
- [The ask door](../ASK.md)
- [People](../PEOPLE.md)

## Running the server

- [Install and try](../public/05-install-and-try.md)
- [Self-hosting guide](../SELF_HOSTING_GUIDE.md)
- [Deployment](../DEPLOYMENT.md)
- [Security guide](../SOVEREIGN_SECURITY_GUIDE.md)
- [Versioning](../VERSIONING.md)
- [Node contract](../brainfoundry/NODE_CONTRACT.md)

The code that decides what workers may do: `scripts/cc/cc_agents.py` (agents and the permission file), `scripts/cc/cc-bridge.py` (cards and postures), `scripts/cc/cc-job.py` (jobs), `scripts/cc/cc_spend.py` (the spending record and its limit).
