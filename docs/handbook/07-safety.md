---
title: "Part 7: Safety"
date: 2026-10-18
---

# Part 7: Safety

Your brain can do a lot by itself.
Three gates stay with you, whatever posture or level you choose.

## Gate 1: anything public

Sending an email, posting, publishing a page, marking memory public, turning on public asking.
A write to a connected app always shows a card; the judge can hold one back, but never sends one by itself.
Agents are told that nothing leaves the brain: they propose, you send.
An agent at level 2 publishes its own work to its repository; give that level only where publishing is fine.
Be slow to tick "don't ask again" on anything that sends.

## Gate 2: money above a cap

Set the 30-day limit in Settings, Spending, small budgets per agent, and a limit at your provider ([Part 6](06-costs.md)).
Never tick "don't ask again" on an action that pays.

## Gate 3: deletes

Agents cannot run `rm -rf`, force-publish, or delete branches.
Deleting kinds of actions never offer "don't ask again".
Archive a thread instead of deleting it; a retired agent's file is kept.
Make an export before you delete anything large.

## If a key leaks

A key is anything that lets someone act as you: a provider API key, your sign-in, the console password, a bot token, the brain's own key.

1. Revoke it where it was made first: the provider's dashboard, BotFather for a Telegram bot, the app's account page for a connection.
2. Make a new one and give it to the brain: a new API key in the home-screen card, a fresh sign-in for a subscription; the console password is changed on the server.
3. Check that the brain works with the new key.
4. Look at what happened: the Trace and Permits pages list what was done.
5. If the brain's own key leaked, it can be regenerated, but other brains then see it as new; tell your friends.
6. If you think the whole server is compromised, do not trust anything on it, including its backups; restore from an export kept elsewhere.

Never paste a key into a conversation: the brain refuses to send anything that looks like one, but the conversation itself is remembered.

More: [the security guide](../SOVEREIGN_SECURITY_GUIDE.md), section 5, and [governance and permits](../public/03-governance-and-permits.md).
