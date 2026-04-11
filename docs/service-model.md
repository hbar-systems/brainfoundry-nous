---
title: BrainFoundry — Service Model
created: 2026-04-04
last_verified: 2026-04-10
status: current
authority: high
relocated_from: hbar.world/ops/SERVICE_MODEL.md (2026-04-10)
---

# BrainFoundry — Service Model

Internal spec: what "BrainFoundry crafts your brain" means end to end.
This defines the intake, build, and handoff process for a personally-crafted brain node.

---

## What the service is

A personal sovereign brain node, built and deployed for you by BrainFoundry.

You do not touch the server. You provide intake information. BrainFoundry configures,
deploys, and hands off a running brain tailored to who you are.

Ongoing: the brain runs on your server (or ours if you prefer), costs you only server fees,
and you own the data entirely.

---

## Intake — what you collect from the client

### Required

1. **Identity**
   - Full name (for `BRAIN_OWNER`, persona)
   - Preferred brain name / symbol
   - Primary email (for contact and vault delivery)
   - Domain (if they have one) or decision to use a BrainFoundry subdomain

2. **Professional context**
   - What they do (role, company if relevant, domain expertise)
   - What they're currently working on (projects, goals, ongoing work)
   - Key collaborators or teams (if useful for persona)
   - Tools they use daily (IDEs, apps, workflows)

3. **Cognitive style** (as much as they can give you)
   - How they prefer to think through problems
   - What kind of answers they want (terse / detailed / Socratic)
   - What they want the brain to remember vs ignore
   - Any strong preferences or anti-preferences

4. **Document corpus**
   - What documents / notes they want ingested
   - Can be: Notion export, Obsidian vault, Google Docs export, a folder of text files
   - Optionally, their CV / bio for the identity tier

5. **Model preferences**
   - Do they want to bring API keys? Which providers?
   - Or fully local (Ollama only)?
   - Any specific models they prefer

6. **Server preference**
   - Use their own server (they give SSH access temporarily)
   - Or BrainFoundry provisions a Hetzner node on their behalf

### Optional (enriches persona significantly)

- A few paragraphs written by them: "here's how I think about X"
- Their most important writing (essays, specs, papers)
- Their reading list or recent reads
- What they explicitly do NOT want the brain to do

---

## Build process

### Step 1 — Provision (15 min)

```bash
# On brainfoundry-provisioner-01
python3 provision.py "<Full Name>" "<email@domain.com>"
```

This creates:
- `BRAIN_ID`, `BRAIN_NAME`, `BRAIN_SYMBOL`
- All secrets generated (API key, identity secret, nodeos signing secret)
- ED25519 keypair generated
- `docker-compose.yml`, `.env` written with all values
- `operators.json` initialized with `OWNER-0001`

### Step 2 — Persona configuration (30–60 min)

Edit `api/brain_persona.md` with the intake information.

Structure to fill:
```markdown
## Who I am
[Name, role, domain — written as the brain speaking in first person about its owner]

## What I work on
[Specific current projects, responsibilities, goals]

## How I think
[Cognitive style, reasoning frameworks, preferred response style]

## My context
[Timezone, tools, key relationships, domain vocabulary]
```

Quality signal: could a new collaborator read this and understand who the owner is?
If yes, the persona is done.

### Step 3 — Document ingestion

1. Receive client's document corpus (Notion export, vault, folder, etc.)
2. Organize into RAG tier structure:
   - `identity/` — CV, bio, principles documents
   - `thinking/` — notes, reasoning, active documents
   - `projects/` — current work docs
   - `writing/` — published essays, long-form work
   - everything else at root or in named sub-folders
3. Run ingestion:
   ```bash
   python scripts/ingest_folder.py --dir /path/to/organized-docs
   ```
4. Verify embeddings populated:
   ```bash
   docker compose exec postgres psql -U postgres -d llm_db \
     -c "SELECT COUNT(*), MIN(created_at), MAX(created_at) FROM document_embeddings;"
   ```

### Step 4 — Deploy

```bash
# On target server
docker compose up -d --build

# Verify all containers healthy
docker compose ps

# Smoke test
curl -H "X-API-Key: <key>" http://localhost:8010/health
curl -H "X-API-Key: <key>" http://localhost:8010/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Who am I?", "model": "llama3.2"}'
```

Response to "Who am I?" should surface persona content. If it sounds generic, the persona or ingestion needs adjustment.

### Step 5 — Domain + TLS (if applicable)

If client has a domain:
```
brain.theirdomain.com → :8010 (API)
console.theirdomain.com → :3010 (UI)
```

Use Caddy. See `docs/DEPLOYMENT.md`.

### Step 6 — Handoff package

Deliver to client:
1. **Credentials vault** (secure note or password manager share):
   - API key (`HBAR_BRAIN_API_KEY`)
   - Console URL
   - Server SSH access (if managed by BrainFoundry)
   - Brain public key (safe to publish, for federation)
2. **Quick start card** (1 page):
   - How to access the console
   - How to chat via API
   - How to ingest new documents
   - How to change the persona
3. **Link to SELF_HOSTING_GUIDE.md** for full reference

---

## Quality bar before handoff

- [ ] "Who am I?" returns correct, specific, non-generic response
- [ ] "What am I working on?" surfaces actual projects from the corpus
- [ ] All 6 containers healthy (`docker compose ps`)
- [ ] API authentication working (rejects requests without key)
- [ ] Console UI accessible
- [ ] TLS configured if domain was requested
- [ ] Client can log into console independently

---

## Post-handoff

The brain is theirs. They run it, they own the data.

BrainFoundry's ongoing role (if any):
- Bug reports / issues → handle via standard support
- Corpus updates → client can self-serve with `ingest_folder.py`
- Persona updates → client edits `brain_persona.md` directly
- Node version upgrades → `git pull && docker compose up -d --build`

---

## Time estimate per build

| Phase | Time |
|-------|------|
| Intake review | 15 min |
| Provision + secrets | 15 min |
| Persona writing | 30–60 min |
| Corpus organization + ingestion | 30–90 min (depends on corpus size) |
| Deploy + verify | 20 min |
| Domain + TLS | 15 min (if needed) |
| Handoff package | 15 min |
| **Total** | **2–4 hours** |
