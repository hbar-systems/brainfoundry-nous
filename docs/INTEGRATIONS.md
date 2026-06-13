# Integrations — connect your real world

Created: 2026-06-13

The brain can read your email, calendar, and Drive, chat with you on Telegram,
research the live web, and use any MCP server's tools. Connect these in the
console's **Integrations** tab. Email and calendar use **app passwords / links —
no OAuth.** Everything connected is **read-only** and treated as **untrusted**
(the brain reasons over it but never obeys instructions hidden inside an email,
invite, page, or tool result).

## Email (IMAP) — ~2 minutes, any provider

1. Integrations → **Email**.
2. Enter your email address. The IMAP host auto-fills for Gmail/Outlook/iCloud/
   Fastmail/Yahoo; otherwise type it (e.g. `imap.gmail.com`).
3. Enter an **app password** — *not* your normal password.
   - **Gmail:** turn on 2-Step Verification → [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
     → generate one → paste the 16 characters.
   - Outlook/iCloud/Fastmail: each has an "app password" under security settings.
4. **Connect email.** It logs in to verify; a wrong password is reported immediately.

Then ask the brain: *"summarize my unread email"*, *"any email from <person>?"*.
Tool: `inbox_read`.

## Calendar (iCal link) — no OAuth, any provider

1. In **Google Calendar**: ⚙ Settings → click your calendar under "Settings for
   my calendars" → scroll to **"Integrate calendar"** → copy **"Secret address in
   iCal format"** (it ends in `.ics`). Outlook/iCloud have the same "publish /
   secret ICS" option.
2. Integrations → **Calendar** → paste that `.ics` URL → **Connect**.
   - The brain validates it's a real iCal feed; a calendar *web-page* URL is rejected.

Then ask: *"what's on my calendar this week?"*. Tool: `calendar_read`.
(Recurring/RRULE events aren't expanded yet — concrete events show fine.)

## Telegram — chat your brain from your phone

1. In Telegram, message **@BotFather** → `/newbot` → name it → copy the token.
2. Integrations → **Telegram** → paste the token → **Connect** (the brain
   registers a secret-protected webhook).
3. Open your new bot, send any message — the **first chat becomes the owner**;
   strangers are refused. Ask it anything; it answers from your brain + reasoner.

Requires the brain's public API to be reachable over HTTPS (`PUBLIC_API_BASE`,
default `https://<your-brain>`).

## MCP servers — connect any tool

1. Integrations → **MCP servers** → enter a name + the server's **HTTP endpoint
   URL** (Streamable-HTTP transport) + an `Authorization` header if it needs one.
2. **Connect server** — the brain handshakes, lists the server's tools, and makes
   them available to the agentic loop as `mcp__<server>__<tool>`.

Security: **you** connect servers — the model can't. Connecting a server grants
its tools to the agentic loop, so only connect servers whose tools you'd want the
brain to call. Tool output is treated as untrusted. (See THREAT_MODEL.md.)

## Google Drive (optional, OAuth)

The one connector that still needs OAuth (Drive has no app-password path). Only
needed for file search — email and calendar are handled above without OAuth.
Enable the Drive API in Google Cloud, add yourself as an OAuth test user, create
a Web client with redirect `https://<your-brain>/integrations/google/callback`,
and paste the Client ID/Secret in the Integrations tab. Tool: `drive_search`.

---

## Prerequisites for the brain to *use* these
- **Web search on** (Settings → Web search, with a Brave key) — this is the v0
  standing authorization for all YELLOW external-read tools, including the
  integrations above, in agentic mode. Also powers Deep Research.
- **Agentic tools on** (Settings → Agentic tools) — lets the model decide when to
  call a tool. A frontier model (BYOK) drives these best.

## Related tabs
- **Research** — Deep Research: ask a question, the brain plans searches, reads
  multiple sources, and writes a cited report (live).
- **Tasks** — add tasks/reminders, or tell the brain "remind me to … tomorrow";
  a due time pings your connected Telegram.
