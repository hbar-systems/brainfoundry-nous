# SOVEREIGN_SECURITY_GUIDE.md

A practical guide for running your brain securely — what's already locked down, what you control, what you're responsible for.

> If you're setting up a brain for the first time, read [SELF_HOSTING_GUIDE.md](./SELF_HOSTING_GUIDE.md) first.
> This guide picks up after that — it's about *operating* a brain securely once it's live.

**Created:** 2026-04-29
**For:** brain operators (the person whose name is on the brain — the buyer / self-hoster / you)
**Not for:** federation peers, contributors to the codebase, or BrainFoundry as a service.

---

## 1. The sovereignty model — what it actually means

A "sovereign brain" makes one specific promise: **the people who built BrainFoundry cannot read your data, change your brain's behavior, or revoke your access.**

Three properties make this real:

1. **Your brain runs on a server you control.** It's your Hetzner instance (or wherever you host). You hold the SSH key. You can shut it down, copy its data, move it to another provider, or destroy it — without asking us.
2. **Your data lives on your server.** Documents you ingest, chats you have, your persona, your federation keypair — all in PostgreSQL on your disk. We don't have a copy. We can't subpoena ourselves into having one.
3. **Your model API keys (if you BYOK) live in your `.env`.** When you chat with Claude or GPT, your brain calls Anthropic or OpenAI directly. Your brain talks to your provider on your behalf. We're not in that path.

**What we DO have access to:**
- Your billing email (for receipts and provisioning failures)
- DNS records for `*.brainfoundry.ai` (so subdomains route correctly — we host the zone)
- The fact that a brain exists at your subdomain (the public reverse-proxy is visible)

**What we DON'T have access to:**
- The contents of any chat
- Any document you ingest
- Your model API keys
- Your brain's persona or behavior
- Your SSH key (you have the only copy — see §4)
- Your console password (random, generated on your server, sent only to you in the welcome email)

**What we technically COULD do (and the tradeoff you choose):**

The provisioner SSHes into your brain with an automation key during initial deploy. After provisioning, that automation key REMAINS in your brain's `~/.ssh/authorized_keys`. This is intentional and gives you a real choice:

**Convenience mode (default — automation key intact):**
- We can SSH into your brain to help if you ask (e.g. you lost your SSH key — see §5.1).
- We will not access your brain without your written request via `hello@hbar.systems`.
- Trust model: you trust BrainFoundry not to abuse access we technically have.

**Full sovereignty mode (you remove the automation key):**

```bash
nano ~/.ssh/authorized_keys
# Delete the line containing "brainfoundry-automation"
# Save: Ctrl+O, Enter, Ctrl+X
```

- We physically cannot reach your brain. No exceptions.
- Trust model: you trust nothing — the math protects you, not our promises.
- **Cost:** if you ever lose your SSH key, your brain is permanently unrecoverable from the outside. We'd have to re-provision a fresh brain at your subdomain and you'd lose all data inside the old one (chats, documents, federation identity).

Pick whichever model fits your threat profile. Most operators choose convenience mode initially and switch to sovereignty mode once they're confident managing keys themselves.

---

## 2. What's already secured for you (the defaults)

When your brain was provisioned, cloud-init applied these defaults at first boot:

| Hardening | Detail |
|---|---|
| SSH key-only login | Password authentication disabled. Only your SSH key works. |
| Root login disabled | `PermitRootLogin no` — even with a key, no direct root access. |
| Modern SSH crypto only | KexAlgorithms, Ciphers, MACs pinned to current best — no legacy fallback. |
| fail2ban | 5 failed SSH attempts in 10 min → 1 hour ban for that IP. |
| ufw firewall | Default deny incoming. Only ports 22 (SSH), 80 (Caddy → HTTPS redirect), 443 (Caddy TLS) open. |
| Docker port binding | All container ports bound to `127.0.0.1`. The only public ingress is Caddy. |
| Sysctl hardening | TCP syncookies, rp_filter, no source-routing, no ICMP redirects, dmesg restricted. |
| Login banner | `/etc/issue.net` shows the "private brain — authorized access only" warning. |
| Console basicauth | `console.<your-brain>.brainfoundry.ai` requires the password from your welcome email. |
| Federation handshake | Inbound federation traffic is signed-and-verified by ED25519 keypairs (see §6). |

**You don't need to do anything to get these.** They're applied before your brain accepts its first request.

---

## 3. What only you control (and how)

### 3.1 Your console password

In your welcome email under "Console password:". This unlocks the web console at `console.<your-brain>.brainfoundry.ai`.

- **Save it in a password manager** (1Password, Bitwarden, KeePassXC, etc.) — we won't email it twice.
- **Lost it?** SSH into your brain, look in `/home/hbar/brain/.env` — `BASIC_AUTH_PASSWORD=...`.
- **Want to change it?** Edit `BASIC_AUTH_PASSWORD` in `.env`, then `cd /home/hbar/brain && docker compose up -d --build api`.

### 3.2 Your SSH key

The `brainfoundry-<your-brain>.key` file from your welcome email attachment.

- **This file IS your brain.** Anyone who gets it logs in as you and reads everything.
- **Set permissions to 600 immediately:** `chmod 600 ~/.ssh/brainfoundry-<your-brain>.key`
- **Don't share, don't email, don't paste into chat, don't commit to git.**
- **If lost or compromised:** see §5 (Compromise response).

### 3.3 Your model API keys (BYOK)

If you added an Anthropic / OpenAI / Groq key to `/home/hbar/brain/.env`:

- The key is in plaintext in your `.env` file on your server. **Restrict access:** `chmod 600 /home/hbar/brain/.env` (already 600 by default).
- Your brain uses the key to call your model provider directly. Requests look like they come from your server's IP.
- **We never see your key.** It's never transmitted to us, never logged outside your server.
- **You pay your provider directly.** No BrainFoundry margin. Your bill is from Anthropic or OpenAI, not us.

### 3.4 Your federation keypair

In `/home/hbar/brain/.env` as `BRAIN_PRIVATE_KEY` and `BRAIN_PUBLIC_KEY`.

- **The private key signs your brain's outbound federation messages.** Other brains verify your identity by your public key.
- **Don't share the private key.** Public is fine — that's literally what gets shared in handshakes.
- **If compromised, regenerate:** `cd /home/hbar/brain && python3 scripts/generate_keypair.py` — but understand this resets your federation identity (other brains will see you as a new entity).

---

## 4. Updating your brain safely

Your brain pulls updates from the public template at `github.com/hbar-systems/brainfoundry-nous`. To pull the latest:

```bash
ssh -i ~/.ssh/brainfoundry-<your-brain>.key hbar@<your-brain>.brainfoundry.ai
cd /home/hbar/brain
./scripts/update_brain.sh
```

The script:
1. Backs up your `.env` (timestamped, kept for rollback).
2. Pulls latest from GitHub.
3. Rebuilds Docker containers.
4. Health-checks the result.
5. **Restores `.env` if anything fails.**

**What persists across updates** (volume-backed, won't be lost):
- All chat sessions
- All ingested documents and their embeddings
- Ollama models you've pulled
- BrainKernel state (governance permits, audit log)

**What gets replaced** (code-only):
- Python source in `/home/hbar/brain/api/`
- UI source in `/home/hbar/brain/ui/`
- Scripts in `/home/hbar/brain/scripts/`

**When NOT to update:**
- During an active session you don't want to lose context for (chats survive but the running container restarts, ~30 sec downtime).
- If you've made local code changes — `git pull` will fail with merge conflicts. Either commit your changes to a fork, or revert before pulling.

**Rollback if something goes wrong:**

```bash
cd /home/hbar/brain
git log --oneline -5    # find the last good commit
git reset --hard <commit-hash>
docker compose up -d --build
```

Volumes still survive. You're rolling back code only.

---

## 5. Compromise response — what to do if something goes wrong

### 5.1 SSH key suspected compromised

1. **Generate a new key on your laptop:**
   ```bash
   ssh-keygen -t ed25519 -f ~/.ssh/brainfoundry-<your-brain>-new.key -N ""
   cat ~/.ssh/brainfoundry-<your-brain>-new.key.pub
   ```
2. **Add the new public key to the brain** (use your old key one last time):
   ```bash
   ssh -i ~/.ssh/brainfoundry-<your-brain>.key hbar@<your-brain>.brainfoundry.ai
   nano ~/.ssh/authorized_keys
   # paste the new public key on its own line
   ```
3. **Test the new key works:** open a new terminal, `ssh -i ~/.ssh/brainfoundry-<your-brain>-new.key hbar@<your-brain>.brainfoundry.ai`. If you get in, proceed.
4. **Remove the old key from `authorized_keys`.** Save.
5. **Delete the old key file from your laptop:** `rm ~/.ssh/brainfoundry-<your-brain>.key`. Move the new one into place: `mv ~/.ssh/brainfoundry-<your-brain>-new.key ~/.ssh/brainfoundry-<your-brain>.key`.

If you can't access the brain to swap keys (old key truly lost):

- **Convenience mode (you kept the automation key — see §1):** email `hello@hbar.systems` with subject "key recovery". We'll SSH in via the automation key, issue you a new key, and confirm. **This is the only scenario where we use that automation key on your brain.**
- **Full sovereignty mode (you removed the automation key):** we cannot help. The brain is unrecoverable from outside. You'd need to re-provision a new brain at your subdomain (email us — we can spin up a fresh one) and re-ingest from your local document copies. Existing chats inside the old brain are lost.

This is the sovereignty/convenience tradeoff stated bluntly. It's also why we recommend backing up your SSH key to a password manager *immediately* upon receipt — long before you decide which mode you want.

### 5.2 Console password suspected compromised

Edit `/home/hbar/brain/.env` → change `BASIC_AUTH_PASSWORD` to a new random value (32 hex chars: `openssl rand -hex 32`), then `docker compose up -d --build api`.

### 5.3 Model API key suspected compromised

1. **Rotate at your provider first** (Anthropic / OpenAI dashboard → revoke old key, create new).
2. Edit `/home/hbar/brain/.env` → replace the old key with the new one.
3. `docker compose up -d --build api`.
4. Verify your brain can chat using the new key.
5. Delete the old key from the provider entirely.

### 5.4 Brain server suspected compromised (full host)

If you suspect the *server itself* is compromised (someone got root, mining script running, weird outbound traffic):

1. **Don't trust anything on the host.** Even backups taken from a compromised host could be tainted.
2. **Federation key:** consider compromised. Regenerate after recovery (§3.4). Notify federated peers.
3. **Spin up a new brain** at a different subdomain via the provisioner.
4. **Re-ingest documents from your local copies** (not from the compromised brain).
5. **Destroy the old server** at the cloud provider.

This is the worst case. None of the security defaults make this impossible — they just make it much less likely. Your job as operator is to keep the SSH key safe, not run shady scripts as root, and update regularly so kernel CVEs get patched.

---

## 6. Federation security — when other brains connect

Federation = brains talking to other brains via signed handshakes. Your brain has a public/private ED25519 keypair generated at provision time. To federate with another brain, both sides verify each other's signatures using public keys.

**The protocol (high level):**

When another brain wants to talk to yours, it sends a federation handshake:

```
POST https://<your-brain>.brainfoundry.ai/v1/federation/assertion
{
  "signed_by": "<their_public_key>",
  "signature": "<ed25519_signature>",
  "payload": { ... }
}
```

Your brain verifies the signature against the public key, logs the interaction in the BrainKernel audit trail, and decides whether to respond based on your trust policy.

**Three privacy modes — pick what fits you:**

**1. Solo mode** — never federate. The protocol is opt-in-shaped. To turn federation off entirely, either firewall `/v1/federation/*` at ufw, or remove the federation routes from Caddy. Your brain is invisible to all other brains. No discovery, no handshakes, no public surface.

**2. Private federation** — federate only with specific brains you know. You exchange public keys with the other operator out-of-band (email, Signal, in person), add their key to your trust list, and your two brains can talk. **You do NOT need to be on any public registry.** Two friends with brains can federate by direct key exchange and never appear on any public list. This is the "sovereign federation" mode.

**3. Public discoverable federation (opt-in)** — appear on the [Wall of Brains](https://hbar.social) (planned, not yet live as of 2026-04-29). The Wall lists brain handles, optional bios, and last-seen timestamps. Other brains can find you and request a handshake; you still control whether to accept. The Wall is **strictly opt-in display**. If your brain is provisioned today, it does NOT appear on the Wall by default.

**Federation does NOT require being on the Wall.** The Wall is a social/discovery feature on top of the federation protocol. Federation is just brains exchanging signed messages. You can have a fully-federated brain with zero public visibility.

**BrainKernel governance** — your brain's BrainKernel logs every federation request, rate-limits inbound calls, and can be configured to refuse based on content patterns. Audit log lives in `nodeos_data` postgres volume; you can review who's tried to talk to your brain and what they said.

**A note on what's built vs planned (as of 2026-04-29):**

- ✓ ED25519 keypair generation per brain
- ✓ `/v1/federation/assertion` endpoint with signature verification
- ✓ Caddy config exempting federation routes from console basicauth
- ✓ Audit logging to BrainKernel
- ⏳ Wall of Brains (`hbar.social`) — opt-in public discovery, not yet live
- ⏳ Trust list / peer allowlist UI — currently config-file based, console UI planned
- ⏳ Federation content policy DSL — currently rate-limit only, richer policy planned

---

## 7. Editing your brain — what's safe to change

You own this brain. You can edit anything. But some changes are safer than others.

### Safe — no risk of losing data

- **Persona** (`/home/hbar/brain/api/brain_persona.md`) — change how your brain speaks, what it emphasizes. Edit, then `docker compose restart api`.
- **Memory layers** (Console → Settings → Memory layers) — rename, add, remove. Existing chunks are preserved; they just may not be auto-retrieved if you remove a layer they're tagged with.
- **Model selection** (Console → Chat → model dropdown) — switch any time. Affects only future replies.
- **Adding new docs** (Console → Knowledge tab) — additive, never destructive.
- **`.env` API keys** (BYOK) — add, remove, change. Restart api after.

### Risky — might break things, but won't lose data

- **Editing API code** (`/home/hbar/brain/api/main.py`) — if you break a route, that route stops working. Other routes keep working. Use `git diff` before committing your changes.
- **Editing UI code** (`/home/hbar/brain/ui/`) — broken UI doesn't break the brain. Worst case, you can't access the console; SSH still works.
- **Changing Docker settings** (`/home/hbar/brain/docker-compose.yml`) — restart could fail; existing containers keep running until you actually restart.

### Dangerous — can destroy data

- **Removing Docker volumes** (`docker compose down -v` — note the `-v`!) — DELETES postgres, ollama models, kernel state, redis. Treat as nuclear.
- **Editing PostgreSQL directly without a transaction** — could corrupt embeddings or kernel state.
- **Running migrations from the wrong commit** — could leave schema in a state your code doesn't expect.

### Never do this

- Commit your `.env` to git.
- Run `chmod 777` anywhere in `/home/hbar/brain` to "fix permissions."
- Disable `fail2ban` or `ufw` "to debug" without re-enabling.
- Pipe a script from the internet straight to bash without reading it.

---

## 8. What we (BrainFoundry) DO and DON'T do

### What we do

- Provision your brain (one-time, at signup) and email you the credentials.
- Host DNS for `*.brainfoundry.ai` so your subdomain routes to your server.
- Maintain the public template at `github.com/hbar-systems/brainfoundry-nous`. Updates flow from there to your brain when you run `update_brain.sh`.
- Respond to support requests at `hello@hbar.systems`.

### What we don't do

- **Read your data.** We don't have technical access to anything inside your brain.
- **Charge for inference.** BYOK means your model bill is from your provider. Sovereignty mode is free (just your hardware cost).
- **Send updates to your brain without you running `update_brain.sh`.** Pulls are explicit, never silent.
- **Track what your brain does.** No telemetry, no usage analytics, no aggregation. We don't know what you've ingested or how often you chat.
- **Have a "kill switch."** We cannot shut down your brain remotely. The closest thing we could do is remove your DNS record at Cloudflare — but your brain's IP would still serve directly, and you could re-point DNS yourself elsewhere. **In full sovereignty mode (§1), even SSH access is denied to us.**

### Honest disclosure

If you're in **convenience mode** (you kept the provisioner's automation key in `authorized_keys`), we technically *could* SSH into your brain. We don't, and we won't without a written request from you. But the technical capability exists until you remove the automation key. We tell you this rather than pretending it's not there. If that bothers you, switch to full sovereignty mode (instructions in §1).

---

## 9. Questions, support, contributing

- **Support / problems:** `hello@hbar.systems` (subject prefix recommended: "support" or "security")
- **Security disclosures:** `hello@hbar.systems` with subject "security disclosure" — we'll acknowledge within 48 hours
- **Code contributions:** brainfoundry-nous is public. Open issues / PRs at `github.com/hbar-systems/brainfoundry-nous`.
- **Premium / white-glove:** for fully-local + fast (dedicated GPU/big-RAM tier), email `hello@hbar.systems` subject "premium brain"

---

## Appendix A — quick checklist for new operators

After your brain is provisioned, do these in your first session:

- [ ] Save SSH key to `~/.ssh/`, chmod 600, test it works
- [ ] Save console password in your password manager
- [ ] BYOK: add an Anthropic/OpenAI/Groq key to `.env` (recommended), or accept sovereignty-mode slowness
- [ ] Test chat works (ask "Who am I?" — if you ingested an identity doc, it should answer; if not, it'll honestly say so)
- [ ] Bookmark this guide on your laptop or your brain's docs/
- [ ] Optional: remove the provisioner's automation key from `~/.ssh/authorized_keys` for full sovereignty

After your first week, do these:

- [ ] Run `./scripts/update_brain.sh` once to confirm updates work for you
- [ ] Ingest at least 5 personal documents into the identity layer
- [ ] Start a federation peer (invite a friend with a brain) — or skip if running solo
- [ ] Set a calendar reminder to update monthly (or whenever you read about a CVE you care about)

---

*Your brain is yours. Nobody else has access. That's not marketing — it's the architecture.*
