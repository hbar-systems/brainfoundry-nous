# People

2026-10-17. The People screen (`ui/pages/people.js`) is in the Standard tier: from the first day, friends see who is on the network and write to each other. The Federation page stays the operator tool.

## What it does today

- **Who is on the network**: the brain's known peers (`GET /v1/federation/peers`). Each one shows a handle, the owner's name if the peer's `/identity` disclosed one when it was introduced (`owner_name`, else `display_name`; an unset placeholder or a name that only repeats the handle is dropped), and online or not by `POST /v1/federation/peers/ping`.
- **A conversation per person**: inbox and outbox (`/v1/federation/dm/inbox`, `/outbox`) merged by peer, newest at the bottom. One text box and Send (`/v1/federation/dm/send`). Unread counts come from `read_at`; opening a conversation marks it read (`/inbox/{id}/read`).
- Someone who writes without being among the known peers still shows, marked "wrote to you".
- **Menu**: People sits after Chat in both newcomer and operator modes, only once the brain knows at least one peer. Until then the Apps page says "People: appears when a friend's brain joins".
- No keys, fingerprints or protocol words on screen. A small "details" link opens the Federation page, in operator mode only.

## The trust model is unchanged (DM v0.5)

This screen changes no trust. As `api/federation_dm.py` says, v0.5 is T1-vulnerable:

- **Receiving**: the sender puts its own public key in the message and signs with it. The recipient checks the signature against that key, so a DM claiming to be from "anne" proves only that someone holding *some* key sent it, not that it was Anne's brain.
- **Sending**: the sender fetches the recipient's key fresh from `https://<handle>.brainfoundry.ai/identity` each time. Whoever controls that address at that moment picks the key.

On the Federation page an operator can spot a key that changed; on the People page a newcomer cannot. Plain words on screen make the gap more important to close, not less.

## Next step: v0.6, pinned peers

Pin the peers known at provisioning, so a DM from "anne" is checked against a key pinned when Anne's brain joined, not one fetched or asserted at the moment of the message.

1. **Pin at provisioning.** When a new brain is made, the friends it starts with are written into its peers directory with their public key (the `public_key` that `peers.introduce` already stores in `data/peers.json`). The peers met later go through introduce, which pins the same way.
2. **Receive against the pin.** In `/dm/receive`, look up `from_brain` with `find_peer_by_brain_id`. If a key is pinned, verify the signature against the *pinned* key and reject a message whose `from_pubkey` differs. If no key is pinned, keep the message but mark it unverified ("not among your friends yet" on People), never let it pass as a known friend.
3. **Send to the pin.** In `/dm/send`, take the recipient's endpoint and key from the peers directory when the handle is known, not a fresh `/identity` fetch; fetch only for a handle that is not pinned, and say so.
4. **Changed key.** A pinned peer whose key changes (a rebuilt brain) is re-pinned only by the owner, on purpose, from the Federation page, never silently.
5. **Tests.** A DM from a pinned peer signed with another key is refused; a DM from an unknown brain arrives marked unverified; send uses the pinned endpoint.

Until v0.6 lands, treat People as fit for friends who already know each other off the network, which is the first-day case it is built for.
