---
created: 2026-11-23
---
# Ask hbar: help between brains

hbar 2026-11-23: "if people have problems with their brains they can ask for help through the Federation protocol".

Every console screen has one small button in the bottom-right corner: "Something wrong? Ask hbar". It moves up by itself if a control of the page sits in that corner, so it never covers the chat's send button. The words follow the console language (ui/lib/helpText.js: en, ru, sk, de, el, rue; all but en still need a native read).

## What the member sees

A press opens a panel with a text box for their own words, and a plain list of what hbar will get:

- their words;
- the screen they are on (its route, no query string, so no file name);
- the last few things they pressed (press names from ui/lib/presses.js, routes and command words only);
- the console language and version.

"Nothing else: not your memory, not your chats, not your files." Send signs it and hands it to the helper brain. When the answer comes back, the button shows a dot and "hbar answered", and the panel shows the answer.

If no helper is set, the panel says so plainly and has no Send.

## Setting the helper

On the member's brain, `data/help.json`:

```json
{"helper": "<helper brain id>"}
```

or the env value `BRAIN_HELP_PEER` (it wins). Default: none. The helper must also be a pinned peer on the member's brain, and the member's brain a pinned peer on the helper's (`POST /v1/federation/peers/introduce`, both ways). `{"button": false}` hides the button (for a brain that only helps).

## The records

Both go through the record door (docs/RECORDS.md) with all its checks: pinned peers only, the signature against the pin, 16 kB body cap, the replay guard, the per-sender rate limit, the audit.

| kind | body | rid | ref |
|---|---|---|---|
| `help.request` | exactly `{screen, pressed[], words, lang, console_version}` | `help-<unix seconds>-<12 hex>` | none |
| `help.answer` | exactly `{request_rid, words}` | `<request rid>.answer` | sha256 of the request |

A record with any other field in the body (memory, chat, persona, anything) is refused, by the sender before it signs and at the receiving door. A signed record cannot be stripped without breaking its signature, so refusing is the only honest choice. `screen` must be a route without a query; `pressed` is at most 8 names from the press alphabet; `words` is 1 to 2,000 characters. An answer is accepted only for a help request this brain really sent to that peer, with that hash. One answer per request. A member brain sends at most 10 requests a day.

Help records are not confirmed in the Records tab; they have their own tab.

## Routes (owner key, console only)

| route | side | does |
|---|---|---|
| `GET /v1/help/status` | member | helper set and pinned, the plain message if not, what was asked and the answers |
| `POST /v1/help/ask` | member | `{screen, pressed, words, lang}`; extra fields refused (422); the brain adds its version |
| `GET /v1/help/inbox` | helper | help requests from member brains, with `open` (unanswered count) |
| `POST /v1/help/answer` | helper | `{peer, rid, words}`; signs and sends the help.answer |

No new public route: requests and answers arrive at `POST /v1/federation/record`.

## On hbar's brain

Federation, tab Help, with the count of open requests. Each card shows who asked, their words, the screen, what they pressed, their language and console version, and an answer box with Send.

## Tests

tests/test_federation_help.py: two throwaway brains with fresh keys in temp dirs (one the real app, one a Door), request A to B and back, the console routes, the owner key, unpinned sender, extra fields refused at the door and by the member's own brain, bad values, forged answers, wrong ref, no helper, helper named but not pinned, replay of request and answer, the daily cap, an unreachable helper.
