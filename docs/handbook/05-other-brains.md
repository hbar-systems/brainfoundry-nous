---
title: "Part 5: Other brains"
date: 2026-10-18
---

# Part 5: Other brains

## Federation

Every brain has its own key, a kind of signature it cannot forge for anyone else.
When your brain talks to another brain, it signs, and the other brain checks the signature.
Brains share only what each owner marked public; your private memory never travels.

## People

The People page appears once your brain knows at least one friend's brain.
It lists who is on the network, whether they are online, and one conversation per person.
Someone who writes to you without being among your friends still shows, marked "wrote to you".

An honest limit: today a message proves that someone with a brain key sent it, not that it was your friend's brain.
Use People with friends you also know off the network, and never send passwords or secrets through it.

## The ask door

Another brain, or one of its agents, can ask your brain a question.
The answer comes only from memory you marked public.
If nothing public matches, the reply is "This brain has no public memory on that question.", and no model runs.
The door uses no tools, writes nothing, and changes no memory.

By default only brains you were introduced to may ask.
You can turn on public asking for any brain; it is off unless you switch it on.
Your reasoner can ask other brains for you the same way.
On your box it runs `cc-job ask https://other-brain.example "<question>"`; your brain signs the question, and the reasoner never holds the key.
Every ask out is in the federation log beside the asks that come in.

More: [the ask door](../ASK.md), [People](../PEOPLE.md), [federation](../public/04-federation.md).
