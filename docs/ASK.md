# The ask door

*2026-10-18*

The ask door is a standard way for one brain, or one of its agents, to ask another brain a question.
It follows the [A2A protocol](https://a2a-protocol.org): there is an Agent Card for discovery and a JSON-RPC 2.0 `message/send` call.
Trust works the way brainfoundry federation already works: every ask carries an ED25519 federation assertion signed with the asking brain's key.

## What it is

- `GET /.well-known/agent-card.json` is public and needs no authentication. It returns the brain's A2A Agent Card: its name, a description (the first line of the persona), the url of the ask endpoint, its version, one skill `ask`, and the auth scheme `brainfoundry-ed25519`, which points to `/identity` for the key.
- `POST /v1/ask` takes JSON-RPC `message/send` with one text part in. It returns one text part (the answer) and one data part (`{"citations": [document names]}`).
- `scripts/ask_brain.py <base-url> "<question>"` is the client. It fetches the card, signs with this brain's key, calls the endpoint, and prints the answer and citations.

The answer comes **only** from chunks whose `metadata.scope` is exactly `"public"`.
Retrieval asks for `scope="public"` and never returns local-only rows, and the door filters the result again.
Internal, private and unscoped chunks never reach the model or the reply.
When no public chunk matches, the reply is "This brain has no public memory on that question.", and no model runs.
The door uses no tools, makes no writes and changes no memory.

## The request

```
POST /v1/ask
Content-Type: application/json
X-Brain-Assertion: <token>

{"jsonrpc": "2.0", "id": "1", "method": "message/send",
 "params": {"message": {"role": "user", "messageId": "…",
                        "parts": [{"kind": "text", "text": "What is X?"}]}}}
```

`<token>` is `issue_federation_assertion(...)` from `api/identity/core.py`, the same signer that outgoing federation calls use. It must have:

| claim | value |
|---|---|
| `iss` | the asking brain's `brain_id` |
| `aud` | the answering brain's `brain_id` (from the card's extension params, or `/identity`) |
| `sub` | `"ask"` |
| `iat`, `exp` | `exp` no more than 600 s ahead; the client uses 120 s |
| `jti` | random; a jti that is used twice is refused |
| `qh` | sha256 hex of the question text as UTF-8; this binds the token to this one question |

## Who may ask

1. **Pinned peers.** A brain whose `brain_id` is in this brain's introduced peers (`data/peers.json`, via Settings or `peers.introduce`) or in `known_peers.toml` is verified against its **pinned** public key. A key that the caller supplies never overrides a pin.
2. **Degraded peers.** These are pinned peers that fail the substrate floor (`FEDERATION_SUBSTRATE_GATE`, the same check as `/v1/federation/assertion`). They are refused.
3. **Unknown brains** are refused (403 `unknown_peer`).

The owner can turn on **public asking** (default off):

```
POST /settings/ask  {"public_asking": true}     (API key)
GET  /settings/ask
```

With public asking on, unknown and degraded brains may ask.
An unknown brain sends its own key in `params.metadata.brainfoundry.public_key`, and the token is verified against that key.
This proves the caller holds the key, not who the caller is. The audit log marks such asks as `trust: "public"`.
The client sends the key with `--public-key`.

## How a brain turns it on

The door is live on every brain that runs this version.
Nothing answers until the brain has public-scoped memory.

1. Set `BRAIN_PUBLIC_URL` (for example `https://<your-brain-host>`) so that the card advertises the address peers can reach. Without it the card uses the request's own URL, which is wrong behind a proxy.
2. Ingest or tag the documents you want answerable with `metadata.scope = "public"`.
3. Introduce the brains you trust as peers, or turn public asking on.
4. Make sure `BRAIN_ID` and `BRAIN_PRIVATE_KEY` are set, so this brain can ask others: `python3 scripts/ask_brain.py https://other.example "question"`.

## Limits

- **Rate.** Each caller is rate-limited with the federation limiter (Redis, fail-closed). The key is `ask:peer:<brain_id>` for pinned peers and `ask:key:<public_key>` for public askers. The limits are `FEDERATION_RATE_LIMIT_MAX` per `FEDERATION_RATE_LIMIT_WINDOW` (default 30/60 s) and `FEDERATION_DAILY_MAX` (default 1000/day). A caller over the limit gets HTTP 429 with `Retry-After`.
- **Size.** Questions are at most 4000 characters. Retrieval uses 3 chunks, the model is `PUBLIC_CHAT_MODEL`, and answers are at most 1024 tokens.
- **Audit.** Every ask is written to the federation audit log (`/v1/federation/log`) with `surface: "ask"`. That includes refusals, rate-limited asks and model errors, along with the caller, the trust level, the first 200 characters of the question, the documents used and the outcome.
- **Replay.** The replay cache is in-process and does not survive a restart. Tokens live at most 600 s.
- **Model.** Retrieved chunks are wrapped as untrusted context. A poisoned public chunk can still shape the answer, but it cannot reach tools or memory, because the door has none.

## A2A mapping and gaps

| A2A | here |
|---|---|
| Agent Card at `/.well-known/agent-card.json` | yes, `protocolVersion` 0.3.0, `preferredTransport: JSONRPC` |
| `message/send` | yes; the result is a `Message` (`kind: "message"`, `role: "agent"`), never a `Task` |
| `message/stream`, `tasks/*`, push notifications | not supported (`-32601`); `capabilities.streaming` is false |
| Parts | in: exactly one `text` part. Out: one `text` part and one `data` part with citations |
| `securitySchemes` | `brainfoundry-ed25519`, declared as an `apiKey` in the `X-Brain-Assertion` header |
| Errors | JSON-RPC error objects: `-32700/-32600/-32601/-32602/-32603`, plus `-32010` unauthenticated (HTTP 401), `-32011` forbidden (HTTP 403), `-32029` rate limited (HTTP 429) |

Where A2A conformance and the signature model pulled apart, the signature model won.
These are the gaps:

- **The "API key" is not static.** A2A's `apiKey` scheme expects a credential that a client gets once and reuses. Here the header value is a fresh ED25519 assertion for each question, bound to that question by `qh` and used only once (`jti`). A generic A2A client can discover the door and parse its replies, but it cannot call the door unless it can sign like `scripts/ask_brain.py` does. The rules are carried in the card's `capabilities.extensions` entry `urn:brainfoundry:ask-assertion:v1`, with `required: true`.
- **The key does not come from an OAuth or OpenID flow.** The key lives at `/identity` (`public_key`), and trust comes from the operator pinning it, not from fetching it. The card states this; A2A has no scheme type for it.
- **Self-certified public askers** send their key inside `params.metadata`, which A2A treats as free-form. This is an extension, not an A2A field.
- **The card is not signed.** A2A 0.3 allows signed Agent Cards (JWS). This card is unsigned. Its authority comes from the pinned key, not from the card.
