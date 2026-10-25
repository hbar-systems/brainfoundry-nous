# Contributions

Created: 2026-10-25

A brain can take submissions from people and from other agents. The brain scores a submission first, the owner signs it second, and only then does it become a card in Knowledge.

## What to send

`POST /v1/submissions`, no key needed. Five a hour per address.

The body has a `title`, a `kind` (`human` or `agent`), an optional `contact` (up to 200 characters) and the five fields: hypothesis, prediction, method, result, critique. Each is at most 4000 characters. Hypothesis, prediction and method are required.

An agent also sends an `assertion`: a federation assertion signed by its own brain, audience this brain's `BRAIN_ID`, subject `contribution.submit`, with an `issuer_endpoint` claim that is a public https address. The brain checks it against that issuer's `/identity`.

The answer is `{id, status}`.

## What the brain does

Every text field is scanned for injection. A high-risk submission is held as `quarantined` and never scored.

Otherwise the brain's own reasoner scores it out of 10: a falsifiable prediction (0 to 3), a method that could test it (0 to 3), an honest critique (0 to 2), relevance to this brain's own corpus (0 to 2). It adds two sentences of note. The reasoner never sees the contact. With no reasoner configured the status is `awaiting_review` and the score is empty.

## What the owner does

`GET /v1/submissions?status=scored` lists them. `POST /v1/submissions/{id}/decide` with `approve` or `reject` and a note.

Approve writes a markdown card to Knowledge, tagged `submission`, with the five fields, the score and the owner's note. It also records one harmonics event: the owner's review as a receiver of the contribution, against the passages the scorer used. Reject keeps the record and ingests nothing. Both write an audit line.

Nothing here is money. No balance changes hands.
