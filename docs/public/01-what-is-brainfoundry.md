# What is brainfoundry

brainfoundry builds sovereign personal brains. A brain is a long-lived, model-agnostic AI node that holds your memory, runs governance on its own actions, and speaks to other brains over a federation protocol. It runs on a server you control, under a license you can fork.

## Why a brain, not a chatbot

A chatbot is stateless. You open a window, ask a question, get an answer, and the model forgets you the moment the window closes. The next session starts from scratch.

A brain is stateful. It accumulates what you tell it, indexes what you upload, forms a persistent sense of who you are, and injects that context into every conversation. The underlying language model is interchangeable. The memory, persona, and governance around the model are the node.

The distinction matters because most of what makes assistance useful over time is not the quality of a single response — it is continuity. A brain that has read your notes for six months can answer questions a fresh chat never can, because the context it brings is yours.

## Sovereignty in practice

Sovereignty is not a brand. It is a concrete set of properties the architecture enforces:

1. **Your server.** The brain runs on hardware you rent or own. No shared backend. No multi-tenant pool. One owner per node.
2. **Your data.** Memory is stored in a PostgreSQL instance on your server. Nothing is telemetered to the publisher. There is no central log, no anonymized training pipeline, no shadow copy.
3. **Your keys.** When the brain calls a commercial model provider, it uses your API key against your billing account. When it runs a local model, no external call is made at all.
4. **Your code.** The node is AGPL-3.0 open source. You can clone, fork, audit, modify, and redeploy. If the publisher disappears, your brain continues running.
5. **Your identity.** Each brain generates its own ED25519 keypair at install. The private key never leaves your server. Other brains verify your signatures by fetching your public key from your own identity endpoint.

None of this depends on the publisher's continued cooperation. The software is a clone of a public repository, the data lives on your disk, and the cryptographic identity is self-issued.

## Why this is different from running a local LLM

A common objection: "I can run a model on my laptop with one command. What does this add?"

The model is a commodity. The wrapper is the product.

- **Memory.** Documents are chunked, embedded into a vector store, tagged into named layers (identity, thinking, projects, writing, or whatever you configure), and retrieved as context on every chat. Memory survives container restarts and accumulates for as long as the node is alive.
- **Governance.** A kernel named BrainKernel gates mutations with a two-phase commit: every state change is first proposed, receives a single-use token, and only executes when the same command is re-submitted with the token. Read-only operations run immediately. Every command is logged to an append-only audit trail.
- **Federation.** Brains exchange signed assertions over HTTPS using ED25519. Two sovereign nodes can share context voluntarily, without a central authority and without sharing secrets.
- **Model agnosticism.** The same node can route queries to a local model for privacy, a larger commercial model for quality, or any mix. Switching models is a config change, not a migration.

A bare LLM runtime gives you inference. A brain gives you an operating environment for personal cognition.

## The node is the product

brainfoundry-nous is the reference implementation of the node. It is not a hosted service. It is a repository you deploy under docker compose on a Linux server.

Three populations run the same code side by side:

1. People who buy a spawn through the brainfoundry provisioner and get a running node on day one.
2. People who self-host — git clone, docker compose up, configure.
3. People who fork and diverge.

The only contract that must stay compatible across forks is the federation protocol, so other brains can still verify them. Every deployer chooses whether to follow the main branch, pin a commit, or run their own fork.

## The 30-second version

You own a brain. It runs on your server. It remembers what you tell it, governs its own actions, and can talk to other brains when you allow it. The code is open, the keys are yours, the model is swappable, and the publisher has no back door.

That is the product.
