# Several members on one box

Dated 2026-10-19. Status: built and tested in a sandbox (every host effect stubbed); the cut-over
test on a real box (below) has not been run yet, so the RAM figures are still to be measured.

A brain is single-tenant: one person, one memory, one key. A shared box therefore never puts two
people inside one brain. Each member gets a whole brain stack of their own, their own Unix users,
and their own port block, next to the brain the box already runs. Nothing changes for a box with
one brain: every default is today's.

## Add a member

On the box, as the admin user (the one with sudo and docker, `hbar` on provisioned boxes), from
the brain checkout the box already has:

```
bash scripts/add-member.sh <handle> <n> --dry-run     # read every action; nothing is changed
bash scripts/add-member.sh <handle> <n> --apply
```

`<handle>` is the member's flat handle (lowercase letters and digits, 2 to 16, starting with a
letter). `<n>` is a free port block, 1 to 99. The script refuses a handle or block already in
`/srv/brains/members.tsv`, an existing checkout, user, group, unit or compose project, and a block
with any port already listening. `--apply` then:

1. creates the users `<handle>-cc` (the bridge) and `<handle>-hands` (the reasoner) and the group
   `<handle>-brain`; no sudo, not in docker, homes mode 700;
2. clones the template to `/srv/brains/<handle>`, owned by the admin, group `<handle>-brain`, no
   access for anyone else;
3. writes `.env` from `.env.example` with fresh secrets straight into the file (mode 600; the
   script prints key names, never values) and the federation keypair when the host Python has
   `cryptography`;
4. writes `docker-compose.override.yml` so the member runs no Ollama of its own;
5. starts the compose project `brain-<handle>`;
6. installs `brains-ollama-link.timer` (once per box): every minute the box's one Ollama joins
   each member's network under the name `ollama`;
7. runs `scripts/cc/install.sh` and `scripts/cc/split-hands.sh` for the member (units
   `cc-bridge-<handle>` and `claude-tab-<handle>`, sudoers `cc-bridge-<handle>` and
   `cc-hands-<handle>`, operator token `CC_OPERATOR_TOKEN_<HANDLE>` in `/etc/caddy/cc-<handle>.env`);
8. appends `<handle> <n> <api port> <date>` to `/srv/brains/members.tsv`;
9. prints the Caddy site block for `<handle>.brainfoundry.ai` and `console.<handle>.brainfoundry.ai`.

By hand afterwards: paste the block into `/etc/caddy/Caddyfile` with the member's console password
hash (`caddy hash-password`), `sudo systemctl restart caddy` (restart, not reload: Caddy reads the
new token file only at start), point both DNS names at the box. If the keypair was not written:
`cd /srv/brains/<handle> && docker compose exec -T api python scripts/generate_keypair.py | grep '^BRAIN_' >> .env`
(nothing printed), then `docker compose up -d api`. The member then signs their reasoner in from
their own console, as on any brain.

`--update-tab` also mounts the docker socket into the member's api so the console's Update tab
works. Leave it off on a shared box unless you accept the cost: that socket is root on the host,
so a member whose brain is compromised would hold every member. Without it, the admin updates a
member with `bash /srv/brains/<handle>/scripts/update_brain.sh /srv/brains/<handle>`.

### The port block

Member n: api 8100+10n, ui +1, nodeos +2, postgres +3, public chat +4, terminal +7, bridge +8;
+5, +6 and +9 are spare. Every port listens on 127.0.0.1 only; Caddy is the only way in. Block 1 is
8110 to 8118. Today's single brain keeps 8010, 3010, 8001, 54332, 3020, 11435, 7681 and 7682,
which no block touches.

The numbers live in two twins kept equal by the tests: `scripts/cc/member.sh` (sourced by the
scripts) and `scripts/cc/cc_member.py` (the bridge, `scripts/member_env.py`).

## What is walled, and how

| | Wall |
|---|---|
| Memory | Each member's own Postgres volume (`brain-<handle>_postgres_data`), own redis, nodeos and api volumes: compose prefixes every volume with the project name. No shared database, no tenant column. |
| Keys | Own `.env` (mode 600, admin only): own api key, identity secret, nodeos secrets, Postgres password, federation keypair. Each brain is its own federation peer. |
| Network | Own compose network. The member's containers cannot reach another member's: the only container on two networks is the shared Ollama. |
| Code | `/srv/brains` is 711 (no listing); each checkout is 2750, group `<handle>-brain` = that member's two users and the admin, readable by the group and never group-writable: `update_brain.sh` and `revert_brain.sh` run under umask 027 for a member's checkout, so the member's hands cannot edit a file root later runs (`install.sh` reruns as root when an update changes it). Update a member only through those scripts, never a bare `git pull` with the admin's default umask. |
| Unix | `<handle>-cc` and `<handle>-hands` have no sudo and are not in the docker group (docker is root on the box). Homes 700; `split-hands.sh` then opens the hands' home 750 to its own bridge, through a group with that bridge as its only other member. A member's hands cannot read its own bridge's state, as on every CC box. |
| Root verbs | A member's bridge gets exactly four, no wildcards: restart and status of `cc-bridge-<handle>` and `claude-tab-<handle>`. The single-brain verbs (`journalctl *`, `systemctl status *`, `docker ps *`, `brain-write`, the root Update) are not given: the first three read other members' units, the last two could rewrite what root runs next. |
| Console | Own Caddy site with its own login. The CC and terminal routes carry the member's own operator token, which only Caddy adds; another member's console cannot present it. |
| Terminal door | Runs as `<handle>-cc`, never as the admin: a member's console never holds an admin shell. |
| Update | `update_brain.sh <checkout>` touches only that checkout, its own compose project (from `COMPOSE_PROJECT_NAME` in its `.env`), its own api image and container, and checks its own api port. The console's Update tab passes its own checkout. |

## What is shared

- **Ollama**: one model server, the first brain's container, published on 127.0.0.1 only. The
  weights are read-only and cost nothing in privacy; prompts pass through it, so it must keep no
  prompt logs on disk. It sits on every member's network, so it is the one thing that could
  bridge them: run nothing else in that container.
- **Docker images and build cache**: identical layers are stored once.
- **The kernel, CPU, RAM and disk**: one member's heavy turn slows the others.
- **Caddy**: one process, one site block per member.
- **The admin**: runs every stack and can read everything, as root always can.

## Remove a member

Export or back up first if the member's memory should survive
(`BRAIN_DIR=/srv/brains/<handle> bash scripts/backup_brain.sh`, or `scripts/export.sh`).

```
cd /srv/brains/<handle> && docker compose down            # add -v to delete the member's memory
for u in cc-bridge claude-tab cc-bridge-watch cc-install-watch cc-work-pull; do
  sudo systemctl disable --now $u-<handle>.service $u-<handle>.path $u-<handle>.timer 2>/dev/null
  sudo rm -f /etc/systemd/system/$u-<handle>.{service,path,timer}
done
sudo systemctl daemon-reload
sudo rm -f /etc/sudoers.d/cc-bridge-<handle> /etc/sudoers.d/cc-hands-<handle>
sudo rm -f /etc/caddy/cc-<handle>.env /etc/systemd/system/caddy.service.d/cc-<handle>.conf
# remove the two site blocks from /etc/caddy/Caddyfile, then:
sudo systemctl daemon-reload && sudo systemctl restart caddy
sudo userdel -r <handle>-cc && sudo userdel -r <handle>-hands && sudo groupdel <handle>-brain
sudo mv /srv/brains/<handle> /srv/brains/.removed-<handle>-$(date +%F)   # or delete it
# delete the member's line from /srv/brains/members.tsv: the block is free again
```

Then the DNS names. The Ollama link timer drops the network by itself (it no longer exists).

## The cut-over test (before anyone moves in)

One scratch member, `test1`, beside the brain a box already runs. Not on hbar's own box: use a
test box with a brain on it (an hourly one is enough). About an afternoon.

1. `free -m` and `docker stats --no-stream` with only the existing brain: the baseline.
2. `bash scripts/add-member.sh test1 1 --dry-run`, read it, then `--apply`.
3. Checks: `curl -fsS 127.0.0.1:8110/health`; `docker compose -p brain-test1 ps`; inside the api,
   `curl -fsS http://ollama:11434/api/tags` lists the shared models; `sudo -u test1-hands cat
   /srv/brains/test1/.env` is refused; `sudo -u test1-cc ls /home/hbar` and `/home/hands` are
   refused; `sudo -l -U test1-cc` shows only the four verbs; `split-hands.sh verify` with
   `CC_MEMBER=test1 CC_MEMBER_N=1`.
4. Paste the Caddy block (a throwaway subdomain), restart caddy, open the console, sign the
   reasoner in.
5. RAM idle: `free -m` and `docker stats --no-stream`, ten minutes after start.
6. RAM during one CC turn: start a turn that reads a few files, and sample `free -m` and
   `ps -o rss= -u test1-hands | paste -sd+ | bc` every 2 s while it runs; keep the peak.
7. Update: `bash /srv/brains/test1/scripts/update_brain.sh /srv/brains/test1` updates only
   `brain-test1` (the first brain's containers keep their start times).
8. Remove the member (above) and check that nothing of it is left.

Write the numbers into hbar.world's next-brains design note; they replace the estimates there.

## Not covered yet

- The terminal door gives the member a shell as their own bridge user, which holds the bridge's
  state (their own tokens). Good enough for the owner; a door that is only the sign-in flow would
  be tighter.
- `split-hands.sh` writes the operator token into the bridge's env file through a `sudo sh -c`
  command line, which other users on the box can see in the process list for that instant
  (unchanged from the single brain; on a shared box it matters).
- The provisioner does not know about members; this is an admin step on an existing box.
- The first brain's checkout stays as provisioned (`/home/hbar/brain`: code readable through the
  751 home, `.env` 600): a member's users can read that brain's code, not its secrets or memory.
