# Who reads what

*Created 2026-10-16. A one-page map. The reasons and the limits are in the previous document, "Privacy and memory". Updated 2026-10-16: brain-apps row, after the app lane closed the gap.*

Each row is someone or something that can read part of your brain. Each column is a kind of thing the brain holds.

- **Open memory:** chunks at the default level.
- **Local-only memory:** chunks you marked local-only, vault documents included.
- **Vault files:** the original files in the vault folder.
- **World and desk files:** your world checkout, `in/` (what you attached) and `out/` (what the reasoner made).
- **Chat history:** the brain's saved conversations.
- **Secrets and keys:** the brain's `.env`, provider keys, the API key, sign-in files.

The "seats" are the Claude Code and Codex reasoners in the CC tab. Both run as the `hands` user on the server. The table assumes a server split into two users (the CC bridge as `cc`, the reasoners as `hands`) and a vault set up with `scripts/vault-setup.sh`.

| Reader | Open memory | Local-only memory | Vault files | World and desk files | Chat history | Secrets and keys |
|---|---|---|---|---|---|---|
| You in the console | yes | yes, on the Knowledge tab | as memory only; the files themselves only on the server, as yourself | yes, in the Files pane | yes | not on any page; yes through the Terminal tab, a shell as the brain user |
| Chat model, local | yes | only if it is on your list and the answer comes back to the console | only as local-only memory, same rule | no; only what was ingested as memory | the current session | no |
| Chat model, hosted | yes | no | no | no; only what was ingested as open memory | the current session, unless it is marked local-only | no; your key pays for the call but is not in the prompt |
| Claude seat | yes, in its memory block | no | no | yes, all that `hands` can read; reads outside its working folders ask first | its own CC threads | its own sign-in, tool-pack keys, the GitHub push token; not the brain's `.env` or the bridge's settings |
| Codex seat | yes, in its memory block | no | no | yes, all that `hands` can read, without asking | its own threads, and anything in `hands`' files, which include Claude Code's session files | `hands`' sign-in files (`~/.claude`, `~/.codex`); not the brain's `.env` or the bridge's settings |
| Brain-apps | only the layers the app asks for, through `llm.complete` | no | no | no | no | no |
| Telegram, the brain's bot | yes | no | no | no | no; each message is answered on its own | no |
| Public visitors | only the `public` layer | no | no | no | only their own conversation | no |
| Other brains | only the `public` layer | no | no | no | no | no |
| Anyone with the brain's API key | yes | yes | as memory only | no | yes | no; the API never returns keys |
| Root, admin, the `docker` group | yes | yes | yes | yes | yes | yes |

Notes on three cells:

- **Brain-apps.** Since 2026-10-16 an app runs in a sealed frame with no web address of its own, and the console refuses its requests, so the app cannot use your API key. It reaches the brain only through the console page, which checks what you approved at install; none of that returns local-only memory. Before that date an app could reach what the API key reaches. One exception remains: an app that ships server code (`entries.api`) runs it inside the brain's API with the API's authority. Read that code before installing.
- **Telegram.** The CC tab has its own Telegram bot, separate from the brain's. A message to that bot is a turn of the Claude seat, so the Claude seat's row applies. Both bots' messages pass through Telegram's servers.
- **Seats.** What a seat reads is sent to its company: Anthropic for Claude, OpenAI for Codex.
- **"Public" is two fields today.** Public visitors: the public chat retrieves by `metadata.layer` and checks `metadata.scope` only when `PUBLIC_CHAT_SCOPE` is set (recommended `public`). Other brains: the ask door keeps only chunks whose `metadata.scope` is exactly `public`. A chunk marked public in one field and not the other is visible to one door and not the other. Unifying them is planned.

## How to keep something truly private today

1. Put the file in the vault, not in the world checkout, `in/` or `out/`, and check the wall with `scripts/vault-setup.sh --check`.
2. Read it only with a local model on your list, in the console, in a fresh session.
3. Never switch that session to a hosted model; start a new session for hosted work.
4. Keep the brain's API key out of reach of `hands` and `cc`, and read the server code of any app that ships some (`entries.api`).
5. Store backups as carefully as the server itself, because a backup holds everything in plain text.
