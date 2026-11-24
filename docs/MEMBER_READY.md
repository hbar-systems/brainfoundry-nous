# A member brain is ready (MEMBERS-11, 2026-11-23)

Created: 2026-11-23. The operator's word: one standard for every member brain.

Ready means the member opens it and their daily work is the first thing they can press, and it is easier than what they did before (ChatGPT, their computer). A green update, a sign-in or a health check never makes a brain ready on its own.

Check: `bash scripts/member-ready.sh <handle> <lang> [<start-page-sha12>]` on a shared box, `--single <lang> [sha]` on the member's own box. Read only. It prints one GREEN or RED line per item and a sum.

| # | item | green when | why it is on the list |
|---|---|---|---|
| 1 | up | console 200, api /health 200, bridge answers | nothing else counts without it |
| 2 | current | checkout HEAD = origin main | fixes in the template reach the member only through an update |
| 3 | persona | over 200 chars in the api's runtime copy and in the checkout copy the console reads | two members (2026-11-22, 11-23) had their persona only in the api, so the console chat ran with none (the bridge now falls back to GET /persona) |
| 4 | language | console layout lang = the member's language | a member reads the console in their own language; the console offers en and ru only (de owed) |
| 5 | first screen | layout start /apps/week, Week app on, quiet layout, start page = the world copy | a stock console (generic title, the full menu) does not tell the member it is theirs |
| 6 | work first | the start page has 3 or more starts into the chat | ready means their work is the first press, lures sit below |
| 7 | reasoner | their ChatGPT or Claude seat signed in, or a key | the small local model invents facts in the member's field |
| 8 | their past | at least one imported chat or file from their computer, beyond the seed doc | switching is easy only when their past (chat exports, documents) is already inside |
| 9 | move-in doors | /laptop/agent.sh answers and Caddy opens the import-laptop token paths for their console | without the Caddy lines the "Bring in this computer" line hits the login and fails |
| 10 | AI history | the move-in carries Codex and Claude Code sessions | many members work in Codex or Claude Code; that history should come along |
| 11 | used | the console has turns | the member has the link and the password and has opened it |
| 12 | onboarding time | from the pasted line to the first real answer from their own material under 30 minutes on a 2-vCPU brain (IMPORT-PACE-1, 2026-11-24) | a member's move-in of 1,825 files ran over two days; the first pass (docs/IMPORT.md "Pace") makes the brain useful inside 15 minutes of reading and leaves the rest to the night |

Item 12 is measured, not checked by member-ready.sh: `python3 scripts/import/onboarding_time.py --estimate` (the model at the measured rates: 21 minutes, GREEN) and `--brain <url> --key-file <file>` on a local brain or the rehearsal slot only (synthetic home, the real agent, a planted fact asked back). The live mode has not been run yet.

Items only a person can judge, checked by a render, not by the script: the first screen at 390 and 1440 read as the member would; "what do you know about me" answered with real things; the list of what the operator said about them counted said against shown (kept by the operator, outside this repo).
