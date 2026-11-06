2026-11-06

# Member lifecycle on a shared box

A shared box (docs/MULTI_INSTANCE.md) hosts one brain per member under `/srv/brains/<m>`.
This page is for when a member leaves, when one of their keys leaks, and when they want their data.
Four procedures: (a) remove a member, (b) revoke and rotate keys and tell peers, (c) export a member's data to them, (d) incident response.
Run everything as the box's admin (sudo, docker group) from the admin's own checkout (`/home/<admin>/brain`), never from the member's.
Nothing here prints a secret; where a secret changes, it is generated inside a root shell and written straight into its file.
`m` below is the handle; `D=/srv/brains/$m`.

## What a member is made of

What `scripts/add-member.sh` creates, and what removal must take away:

| thing | where | taken by remove-member.sh |
|---|---|---|
| checkout, `.env` (owner key, federation private key, identity secret, NodeOS secret, Postgres password) | `/srv/brains/<m>` | yes (step 8) |
| compose project `brain-<m>`: containers, volumes (memory, runtime volume with persona and the encrypted settings sidecar holding provider keys and the brain's Telegram token), images, network | docker | yes (step 3) |
| users `<m>-cc` (bridge: `~/.cc-bridge/env` with the operator token, owner key copy, reasoner sign-in, bridge Telegram token), `<m>-hands` (`~/in` uploads, work), group `<m>-brain` | `/home` | yes (step 7) |
| units `cc-bridge-<m>`, `claude-tab-<m>`, watch units | `/etc/systemd/system` | yes (step 4) |
| sudoers `cc-bridge-<m>`, `cc-hands-<m>`, the Update door `brain-update-<m>`, its log dir | `/etc/sudoers.d`, `/var/lib/brain-update/<m>` | yes (step 5) |
| Caddy token file and drop-in | `/etc/caddy/cc-<m>.env`, `/etc/systemd/system/caddy.service.d/cc-<m>.conf` | yes (step 6) |
| Caddy site blocks with the console's bcrypt line | `/etc/caddy/Caddyfile` | yes (step 9): `<m>.brainfoundry.ai`, `console.<m>.brainfoundry.ai`, every block proxying only to the member's port block, and `--site NAME` |
| registry line and the member count | `/srv/brains/members.tsv`, `/srv/brains/count` | yes (step 8) |
| backups made with `backup_brain.sh` | `/home/<admin>/brain-backups/...` | listed only (step 11) |
| Hetzner box backups and snapshots (the whole disk, `.env` included) | the cloud | no: by hand |
| DNS names | the zone | no: by hand |
| peers that pin the member's public key | other brains' `api/identity/known_peers.toml`, `data/peers.json` | no: procedure (b), "tell peers" |
| Telegram bots, provider API keys | Telegram, the providers | no: revoked at the source |
| the operator's records (registry of nodes, identity baseline, incident log) | the operator's private repo | no: by hand |

## (a) Remove a member

1. Decide about the memory, out loud.
   The member's own word first: do they want an export (procedure c), and do they want to be forgotten (backups deleted too)?
   `--apply` refuses unless you pass `--export` or `--no-export`.
2. If the member is leaving because of a leak or abuse, do (b) first for anything that is valid off the box (Telegram, provider keys), then remove.
3. Dry run, read every line:
   ```
   cd /home/$USER/brain
   bash scripts/remove-member.sh $m --dry-run --export
   ```
   Check the line `site blocks to drop:`.
   It lists the two default names and every site block whose local upstreams are all in the member's port block (custom names such as `brain.<their-domain>` are found this way).
   A block that mixes the member's ports with other upstreams is refused before anything is touched: split it by hand.
   Add a block the scan cannot see with `--site NAME`.
4. Apply:
   ```
   bash scripts/remove-member.sh $m --apply --export          # or --no-export, said to the member
   ```
   The carry dir (default `~/member-carry/<m>-<UTC>`, mode 700) then holds the export archive (vault included), `in-<m>.tar.gz` (the hands' uploads), the persona and the console's hash line.
   The script stops before taking anything if the export fails or the Caddyfile is unreadable.
   Step 10 must say `none`; anything listed there is removed by hand.
5. Step 11 prints what stays. Work through it:
   - Backups on the box: step 11 lists folders that name the handle and artifacts whose `manifest.txt` says `brain_dir: /srv/brains/<m>`.
     If the member asked to be forgotten, `sudo rm -rf` each listed artifact after reading its manifest.
     Make member backups with `BRAIN_DIR=$D BACKUP_DIR=/home/$USER/brain-backups/$m bash scripts/backup_brain.sh`: with the default `BACKUP_DIR` they share the admin brain's folders and retention.
   - Hetzner: box backups rotate out after 7 days; snapshots stay until deleted (`hcloud image list --type snapshot`).
     If the member asked to be forgotten, list the snapshots taken while they lived on the box and ask the operator about each (deleting a snapshot is a destructive step: the operator's word).
   - DNS: delete every name on the script's last line.
     Until then the names resolve to the box and Caddy answers with no site for them.
   - Peers and records: procedure (b), "tell peers"; remove the member's row from the identity baseline and the node registry, write a row in the incident log (kind `removal`).
6. Hand over the carry dir (procedure c), then `rm -rf ~/member-carry/<m>-<UTC>`.

Why the port scan matters: a site block left behind keeps routing the old name to the port block, and the next member given that block would be reachable under the old name, behind the old member's console password.

## (b) Revoke or rotate keys, and tell peers

Rotate when a key may have left the box (a leaked `.env`, a stolen laptop with a console session, a member who leaves on bad terms but stays a peer of someone).
Each key, where it lives, how to rotate, what breaks:

**Federation identity key** (`BRAIN_PRIVATE_KEY`, `BRAIN_PUBLIC_KEY` in `$D/.env`; the public half is published at `/identity` and pinned by peers).
```
cd $D
umask 077
docker compose --project-directory $D exec -T api python -c "from api.identity.core import generate_brain_keypair as g; a, b = g(); print(f'BRAIN_PRIVATE_KEY={a}'); print(f'BRAIN_PUBLIC_KEY={b}')" </dev/null > ~/keyrot-$m.txt
nano $D/.env                 # replace the two lines with the two in ~/keyrot-$m.txt; nothing is printed
shred -u ~/keyrot-$m.txt
docker compose --project-directory $D up -d api
curl -s localhost:<api port>/identity | python3 -c 'import sys,json; print(json.load(sys.stdin)["public_key"][:16])'
```
Every peer that pinned the old key now refuses this brain until it pins the new one (below).
After a leak, that refusal is the point: the old key can sign as this brain until every peer has dropped it.

**Console password** (the bcrypt line in the console site block; Caddy basicauth).
```
caddy hash-password          # type the new password twice; prints a hash, not the password
sudo cp -p /etc/caddy/Caddyfile /etc/caddy/Caddyfile.bak-pw-$m-$(date -u +%FT%H%MZ)
sudo nano /etc/caddy/Caddyfile   # in the console block of $m, replace the hash after the user name
sudo caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile && sudo systemctl reload caddy
curl -s -o /dev/null -w '%{http_code}\n' https://console.<name>/   # 401
```
Tell the member the new password by a channel other than the one that leaked.

**CC operator token** (`CC_OPERATOR_TOKEN` in `/home/<m>-cc/.cc-bridge/env`, `CC_OPERATOR_TOKEN_<M>` in `/etc/caddy/cc-<m>.env`; Caddy adds it to every `/cc` and `/claude` call).
The new value is made inside the root shell and never appears on a command line:
```
sudo M=$m bash -s <<'SH'
set -eu
T=$(python3 -c 'import secrets; print(secrets.token_hex(24))')
E=/home/$M-cc/.cc-bridge/env; V=CC_OPERATOR_TOKEN_$(echo "$M" | tr a-z A-Z)
{ grep -v '^CC_OPERATOR_TOKEN=' "$E" || true; echo "CC_OPERATOR_TOKEN=$T"; } > "$E.tmp"
chown "$M-cc:$M-cc" "$E.tmp"; chmod 600 "$E.tmp"; mv "$E.tmp" "$E"
echo "$V=$T" > "/etc/caddy/cc-$M.env"; chmod 600 "/etc/caddy/cc-$M.env"; chown root:root "/etc/caddy/cc-$M.env"
systemctl restart "cc-bridge-$M" "claude-tab-$M" caddy
SH
curl -s -o /dev/null -w '%{http_code}\n' -X POST localhost:<bridge port>/cc/new   # 403 without the token
```
Caddy restarts (not reloads): the token arrives through its environment.

**Owner API key** (`BRAIN_API_KEY` in `$D/.env`, copied into the bridge env by `scripts/cc/install.sh`).
```
umask 077
python3 -c 'import secrets; print("BRAIN_API_KEY=" + secrets.token_urlsafe(32))' > ~/apikey-$m.txt
nano $D/.env                 # BRAIN_API_KEY=<the line in the file>
shred -u ~/apikey-$m.txt
docker compose --project-directory $D up -d
sudo M=$m D=$D bash -s <<'SH'
set -eu
E=/home/$M-cc/.cc-bridge/env
{ grep -v '^BRAIN_API_KEY=' "$E" || true; grep '^BRAIN_API_KEY=' "$D/.env"; } > "$E.tmp"
chown "$M-cc:$M-cc" "$E.tmp"; chmod 600 "$E.tmp"; mv "$E.tmp" "$E"; systemctl restart "cc-bridge-$M"
SH
```
Do not rotate `BRAIN_IDENTITY_SECRET` as part of this: it encrypts the settings sidecar, and a new one makes every stored provider key and the Telegram token unreadable (they must then be entered again).

**Provider and model keys** (entered by the member in Settings, Keys; stored encrypted in the sidecar).
Revoke at the provider's console first: that is the only revocation that counts once a key may have left.
Then clear it on the brain: Settings, Keys, empty the field (or `POST /settings/keys` with `{"provider": "<p>", "key": ""}` and the owner key), and enter the new one.
A key the operator made for the member (a capped key) is revoked by the operator.

**Telegram.** Two bots may exist.
The brain's own bot (the Integrations page; token in the sidecar): Integrations, Telegram, Disconnect (deletes the webhook and the stored token), then in Telegram `@BotFather`, `/revoke`, pick the bot.
The bridge's bot (`CC_TELEGRAM_TOKEN` in the bridge env): `/revoke` at `@BotFather`, then the new token with `BRIDGE_USER=$m-cc bash scripts/cc/set-env.sh CC_TELEGRAM_TOKEN` and `sudo systemctl restart cc-bridge-$m` (set-env.sh restarts the single brain's `cc-bridge`, not the member's).
A bot belongs to the Telegram account that made it: if the member made it, only the member can revoke it; tell them.
Removing a member without revoking leaves the bot valid with nothing behind it.

**Reasoner sign-in** (`CLAUDE_CODE_OAUTH_TOKEN` in the bridge env): the member signs out of that token on their reasoner account; on the box, `scripts/cc/set-token.sh` as `<m>-cc` sets a new one.

### Tell peers

A peer pins a brain in `api/identity/known_peers.toml` (brain_id, endpoint, public key; mounted read-only by `docker-compose.override.yml`) and may have it introduced in `data/peers.json`.
After a removal, drop the entry; after a rotation, replace the key.
Find every pin on every box you run (each brain: the admin brain and each `/srv/brains/*`):
```
for d in /home/$USER/brain /srv/brains/*/; do
  [ -e "$d/docker-compose.yml" ] || continue
  echo "== $d"; grep -n -B2 -A2 '<brain_id or first 16 of the public key>' "$d/api/identity/known_peers.toml" 2>/dev/null
  docker compose --project-directory "$d" exec -T api cat /app/data/peers.json </dev/null 2>/dev/null | grep -n '<brain_id>'
done
```
Edit a pin with `sudo nano $d/api/identity/known_peers.toml` (back it up beside first), then `docker compose --project-directory $d up -d api`.
Drop an introduced peer from that brain's console (Settings, Security and Federation) or `DELETE /v1/federation/peers/<brain_id>` with that brain's owner key.
For brains you do not run, write to their operator: the brain_id, the old key's first 16 characters, the new key (or "removed"), and the date; ask them to confirm.
Never send a new key over the channel that leaked, and never let a peer take it from `/identity` alone: pins are set out of band.
Then update the operator's identity baseline (the public key each brain is expected to publish), or the tripwire will alert on the new key.

## (c) Export a member's data to them

Consent: an export goes to the member and to no one else, on their own word (a message they sent, kept in the record).
The vault is included only when the member asks for their whole brain; a removal export includes it, since it is theirs.

What is included (`scripts/export.sh`, docs/EXPORT.md): `manifest.json` with row counts, the memory (`db/document_embeddings.jsonl` with embeddings), chats, the persona, governance `.md`, the installed-apps list, introduced peers.
Not included: `.env`, provider keys, the settings sidecar, private keys, audit logs, NodeOS `memory_proposals` (`scripts/export_brain.py` over SSH collects those), the bridge's threads (they sit beside tokens in the bridge's home).
`remove-member.sh --export` adds `in-<m>.tar.gz`, the files they uploaded to the hands.

Best: the member makes it themselves while their console still works: Settings, Export, "Export my brain", Download.
By the admin:
```
BRAIN_DIR=$D INCLUDE_VAULT=1 bash scripts/export.sh ~/member-carry/$m-export      # or remove-member.sh --export
```
Verify before handing it over:
```
A=~/member-carry/$m-export/brain-export-*.tar.gz
tar -tzf $A                                                   # no .env, no settings.json, no keys
tar -xOzf $A manifest.json | python3 -c 'import sys,json; m=json.load(sys.stdin); print(m["contents"]["tables"], m["contents"]["vault"])'
docker compose --project-directory $D exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "select count(*) from document_embeddings"' </dev/null
sha256sum $A
```
The manifest's `document_embeddings` count must match the live count.
Delivery: encrypt with a passphrase you tell the member by voice or another channel (`gpg --symmetric --cipher-algo AES256 $A`), send the `.gpg` by any channel, send the sha256 separately, and ask them to confirm the checksum and that it opens.
Then delete your copy (`shred -u`) and note the date in the record.
Restoring it elsewhere: docs/EXPORT.md, "Restore onto a brain".

## (d) Incident response

Write it down first, then act; the record is the operator's private incident log (for this network: one row per incident in the operator repo's `ops/security/incidents.tsv`, columns and severity scale in `ops/security/INCIDENTS.md` beside it).
A key leak: (b) for the leaked key, tell peers, row with `keys_rotated` and `peers_told`.
A member who must leave now: stop their stack first (`docker compose --project-directory $D stop`, `sudo systemctl stop cc-bridge-$m claude-tab-$m`), revoke what is valid off the box, then (a).
Abuse of the shared box (CPU, disk, Ollama): stop the stack, measure, record, then decide with the member.
Halting a member's hands without removing anything: docs/KILL_SWITCH.md.
