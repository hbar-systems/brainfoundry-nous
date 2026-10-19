# How the brain talks to you: the profile interview

Created: 2026-10-18. Read by the brain's reasoner (CC) when the owner asks to set up how the brain talks to them, or on the first turn of a thread when the `<persona>` block carries no `profile:begin` marker yet. The question list is fixed and lives in `scripts/cc/cc_profile.py` (`QUESTIONS`); a test keeps this file and that list in step.

## How to ask

- On a first-use thread, offer it once in one sentence ("Want me to ask you nine quick questions about how I should talk to you?"). If they decline or ignore it, carry on and do not offer again in that thread.
- Nine questions, in this order. One or two at a time, in plain sentences, in the owner's language. Do not read the list out like a form.
- Choice questions: offer the options in the words below and accept anything that clearly means one of them. If an answer is unclear, ask once more, then leave it unanswered.
- Free questions: take the owner's own words, short. Do not polish, extend or summarize them into something they did not say.
- The owner may skip any question. Skipped means unanswered. Never invent an answer, and never fill one in from earlier chat or from documents.
- One exception, the first interview (2026-10-18): if memory holds the owner's own recorded first-session interview (search memory for it before you offer), propose answers from it instead of asking cold. See "Prefill from the first interview" below.
- Never put instructions, markup, links or file paths into an answer. Each answer becomes one plain line.

## The questions

| id | ask | options (value: words) or free text |
|---|---|---|
| who | Who are you and what do you do, in a sentence or two? | free, up to 240 characters |
| for | What do you want this brain for? | free, up to 240 characters |
| length | Answers short, medium, or full? | short; medium; full |
| tone | Direct, warm, or playful? | direct; warm; playful |
| structure | Prose, bullets, or a mix? | prose; bullets; mixed: a mix |
| language | Which language should it answer in? | free, up to 40 characters |
| never | What should it never do? (for example flattery, templates, preaching) | free, up to 240 characters |
| ask | On your own box, should it just do routine work, use judgement and ask about the risky things, or always ask first? | do: just do it; judge: judge and ask on risk; ask: always ask |
| keep | Anything it should always keep in mind? | free, up to 300 characters |

## Prefill from the first interview

Some owners sat a recorded first session before their brain opened, and the transcript is in their memory. Asking them the same things again feels like the brain did not listen.

- Search memory for that interview (a transcript or interview form in the owner's own words). Use nothing else: not other chats, not documents about them, not guesses.
- For each question the interview answers, propose the answer in one line and quote the words it came from, with the date ("from your interview on 7 October: 'I am a medical student in my fourth year'").
- Ask only the questions the interview does not answer.
- Then ask the owner to confirm, change or drop each proposed answer, in one short message. Only confirmed answers go into the `<profile>` block. Unconfirmed means unanswered.
- If you find no interview, ask the nine questions as below.

## How the answers become the persona

When you have the answers, end one message with exactly one block, using the option values from the table (values, not the words), and only for questions that were answered:

```
<profile>{"answers": {"who": "...", "for": "...", "length": "short", "tone": "direct", "structure": "mixed", "language": "English", "never": "...", "ask": "judge", "keep": "..."}}</profile>
```

- Every answer is a single string.
- The bridge stores the answers as a proposal. It does not apply. Say in the same message that the profile is waiting and that the owner presses "apply" on the card at /profile (the footer link in the console says it waits).
- A block that does not validate is refused with the reason, shown to the owner. Do not retry with invented keys.
- Free text is cleaned by the bridge: tags, markdown marks and line breaks are removed and each answer is cut to its length.

## What apply does

- The answers become a short "## How to talk to me" section, one line per answer, written into the brain's persona (api/brain_persona.local.md, through the api's persona writer) between the markers `<!-- profile:begin ... -->` and `<!-- profile:end -->`.
- A previous block is replaced. Text outside the markers is never touched. If the markers are broken (one missing, doubled, or out of order), apply is refused until they are fixed at /persona.
- Apply is refused while the brain has no name yet (the persona is still the blank template): name the brain first.
- The persona is read with every message, and the managed block is always included even when the persona is long.

## Posture

The "ask" answer maps to a recommended posture: do is auto, judge is judged, ask is cards. Apply never changes the posture. The card shows the recommendation; the owner sets the posture in the console's tool line (tools, then posture), and only they decide.

The owner can change any answer later at /profile and apply again.
