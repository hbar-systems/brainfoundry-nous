---
created: 2026-11-23
---
# The record door

One brain hands another a signed record; the other keeps it, countersigns it, and its owner confirms or declines it with a press. The confirmation goes back the same way, so both brains hold the same rows.

The door does not know what a record means. `kind` and `body` are for the application on top.

## Who can send

Only a pinned peer: a brain introduced on this brain (`POST /v1/federation/peers/introduce`, kept in data/peers.json) or listed in known_peers.toml. The key is the pinned one, never a key carried inside a message. A stranger gets 403 `unknown_peer`.

## Wire

`POST /v1/federation/record` with `{"record": {...}, "sig": "<b64url>"}`.

| field | what |
|---|---|
| v | 1 |
| kind | lower case, `[a-z][a-z0-9._-]{0,63}`; `record.receipt` is reserved; `record.confirm` and `record.decline` only come from the press |
| rid | 8 to 120 of `A-Z a-z 0-9 . _ : -`, unique per sender |
| from, to | brain ids; `to` must be this brain |
| iat, exp | integer seconds; not issued more than 5 min ahead, not expired, at most 30 days apart |
| body | object, at most 16,000 canonical bytes, no floats |
| ref | optional sha256 hex of a record this one answers |
| confirm | optional: the exact text the receiving owner types to confirm (default `confirm`) |

The signature is ED25519 over the RFC 8785 bytes (api/federation_jcs.py). Floats are refused anywhere, so the bytes are the same in every language.

The reply is a receipt signed by this brain: `{v, kind: "record.receipt", rid, from, record_hash, by, at}`. The sender checks it against its own pin of this brain.

## Replay

`(from, rid)` is kept on disk for good. The same record again gets the same receipt; the same rid with other content gets 409. A restart does not reopen the window.

## The owner's press

Owner routes (API key; the console proxy refuses app frames):

| route | does |
|---|---|
| `GET /v1/federation/records` | list, with `answerable` and the `confirm_text` |
| `GET /v1/federation/records/row?peer=&rid=` | the shared row: record, sig, receipt, receipt_sig |
| `GET /v1/federation/records/verify` | re-check the hash chain and every signature |
| `POST /v1/federation/records/send` | sign and deliver a record to a pinned peer |
| `POST /v1/federation/records/redeliver` | try an undelivered record again |
| `POST /v1/federation/records/answer` | the press: `{peer, rid, typed, decline?, note?}` |

Confirming needs the record's confirm text typed exactly; declining needs `decline`. The answer is a record of kind `record.confirm` or `record.decline`, rid `<rid>.confirm` or `<rid>.decline`, `ref` = the answered record's hash. The sender's brain accepts it only if it really sent that record to that peer with that hash, and countersigns it. In the console: Federation, tab Records.

Limit: the press is the API key plus the typed text. Anything holding the brain's API key can press, the same as every other console action.

## Store

Append-only JSONL, hash-chained, mode 600: `FEDERATION_RECORDS_PATH` (default data/records.jsonl). Every inbound call is in the federation audit with surface `record`.

## Tests

tests/test_federation_record.py: two throwaway brains (one the real app, one a Door), the whole loop with identical rows on both sides, the press, pins, impostor keys, tampering, address, time limits, floats, size, forged confirmations and receipts, replay across a restart, delivery that fails and is retried, the store's mode and tamper check.
