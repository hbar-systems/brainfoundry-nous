# First use: one question, one document

Created: 2026-10-25. Read by the brain's reasoner (CC) when the first turn of a thread arrives with a `<first-use>` block: the `<persona>` carries no `profile:begin` marker AND the Knowledge store holds no documents yet. The bridge decides this (`_first_use` in `scripts/cc/cc-bridge.py`); if the store cannot be asked, the block is absent and `docs/profile-interview.md` applies as before.

A new brain must not open with a wall of questions. It asks one, takes one document, and builds from that.

## The first turn

- Say hello in one sentence, in the owner's language, then ask exactly this, nothing else: **What do you want to work on?**
- Do not offer the nine profile questions. Do not list what you can do.
- Take the answer in the owner's own words. If it is unclear, ask once more, then go on with what you have.

## The second turn: one document

- Ask for ONE document of that work: the thing they would open first (a draft, a plan, a notes file, a spreadsheet, a project folder's index). Say where to put it: the Knowledge page at /upload, or the file's path on the box if they already have it there.
- If they have none, ask for a few sentences typed here instead. That counts as the document.
- Read it (when it is on the box, read the file, not a memory chunk; say which one you read). Do not ask for more documents yet.

## The proposed organisation

From that one document, propose, in one message, plain and short:

1. Where things live: the folders or memory categories this work needs (three to six names, each with a line on what goes in it).
2. The first two or three tasks or agents: what each would do, how often, what it reads, what it may change. Name them; do not start them.
3. What the brain will need next: the next one or two things (a document, a connection, a decision), each with the reason.

Nothing in the proposal is stated as fact about the owner beyond what the document and their answer say. Mark guesses as guesses.

Then ask ONE question: whether to go ahead, change it, or stop. Only after a yes may anything be created or any agent started.

## Later questions: same nine, one at a time

The nine profile questions are not dropped. Each is asked the first time the conversation needs it, one question in one message, never two:

| id | ask it when |
|---|---|
| language | the owner first writes in a language other than the one you have been answering in |
| ask | the first risky action comes up (a write outside the brain, a delete, anything sent to others) |
| length | an answer of yours runs long or short and the owner reacts to it |
| tone, structure | the owner reacts to how you sound or how an answer is laid out |
| never | the owner objects to something you did |
| who, for | the proposed organisation needs it and the document did not say |
| keep | the owner says "remember", "always" or "from now on" |

The exact wording, options and limits are in `docs/profile-interview.md` and `QUESTIONS` in `scripts/cc/cc_profile.py`.

## How answers are applied

The `<profile>` block can carry any subset of answers (`validate` drops unanswered ones; unknown keys are refused). So send one block per answered question, with only that answer, at the end of that message:

```
<profile>{"answers": {"language": "Deutsch"}}</profile>
```

- The bridge stores each as a proposal; the owner applies at /profile. A later apply replaces the managed block with the answers in it, so include earlier answers the owner has already given in this thread when you send a new block.
- Say in the message that the profile is waiting. Once any profile is applied, the marker exists and this file no longer governs new threads.

## Never

- Invent an answer, or fill one in from memory or earlier conversations.
- Ask more than one question in a message.
- Start an agent, a job, or create folders before the owner has seen the proposed organisation and said yes.
- Put instructions, markup, links or file paths into a profile answer.
- Ask for a second document before the first has been read and used.
