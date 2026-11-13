created: 2026-11-06

# Member limits on a shared box

A shared box (docs/MULTI_INSTANCE.md) runs several members' brains side by side.
Without limits, one member, its reasoner or one of its jobs can take the whole box: all the memory, all the CPU, every process slot, the disk, or the money behind a key.
These limits keep each member to its share.
A brain alone on its box is not affected: every default limits nothing.

The numbers live in one place, `scripts/member_limits.py`.
`scripts/add-member.sh` writes them for every new member.
Each number can be changed for one run with `BRAIN_LIMIT_*` in the admin's shell (below).

## The layers

**Containers.** Each service of the member's stack (api, ui, nodeos, public-chat, postgres, redis) gets `cpus`, `mem_limit` (the ceiling: past it the kernel kills inside that container only), `mem_reservation` (under cgroup v2 this is memory.low: what the box keeps for this member when memory runs short) and `pids_limit`.
They sit in the member's `docker-compose.override.yml`, which belongs to the admin.
docker-compose.yml reads the same names from `.env` (`BRAIN_LIMIT_API_MEM` and so on) with defaults of 0 and -1, which mean no limit.

**Logs.** Every service rotates its json log at `BRAIN_LOG_MAX_SIZE` x `BRAIN_LOG_MAX_FILE` (20m x 5, so at most 100 MB per container).
This is the one default that applies to every install; containers pick it up when next recreated.

**The reasoner and its jobs.** The member's reasoner and every cc-job run as `<m>-hands` under sudo inside the bridge unit `cc-bridge-<m>` (and the terminal inside `claude-tab-<m>`).
sudo opens no new login session, so they stay in that unit's cgroup.
Both units go into `brain-<m>.slice`: `CPUQuota`, `MemoryHigh` (throttles), `MemoryMax` (kills), `MemoryLow` (kept) and `TasksMax` (every process and thread).
Cron and at would start processes outside the slice, so `<m>-cc` and `<m>-hands` are listed in `/etc/cron.deny` and `/etc/at.deny`.

**Parents.** cgroup v2 honours a reservation only up to what the parent cgroup carries.
So `brain.slice` (the parent of every `brain-<m>.slice`) and `system.slice` (where docker puts every container) carry the sum of their children's reservations: `member_limits.py parent brain|system`.
Without these two files the reservations protect nothing.

**Running jobs.** `CC_MAX_JOBS` caps how many cc-jobs one brain runs at once (scripts/cc/cc_extras.py, `Jobs.start`).
Unset or 0 means no cap, as before.
A value that does not parse means 1.

**Spend.** The spend ledger (scripts/cc/cc_spend.py) already had the owner's own cap, which pauses scheduled agents.
`CC_SPEND_CAP_EUR` adds the admin's ceiling for the last 30 days: the cap in force is the lower of the two, the owner cannot raise it from Settings, and over it the bridge refuses new jobs as well.
The ledger counts what the reasoner reports, an estimate.
The hard limit on money is the provider's own spend limit on the API key the admin hands out (D72); set this ceiling to the same number.
Default: none, because a member signed in with their own subscription pays for it themselves.

Both `CC_MAX_JOBS` and `CC_SPEND_CAP_EUR` live in `/etc/brainfoundry/limits-<m>.env` (root, 644, not a secret).
The bridge's drop-in names it as a second `EnvironmentFile`, read after the bridge's own env file, so the admin's numbers win.

**Disk.** On ext4 a docker volume cannot be given a size, and the containers' files belong to container uids that every member shares, so a user quota cannot tell members apart inside `/var/lib/docker`.
The realistic mechanism is measure and alarm: `sudo python3 scripts/member_limits.py disk` adds up each member's checkout, its two homes and its compose project's volumes, compares them to the quota (`BRAIN_LIMIT_DISK_GB`, 15 GB) and checks that the root disk keeps 10 percent free; it exits 1 on either.
A timer runs it hourly (the operator installs it; see the apply notes in the hbar.world record).
A hard cap on the homes is possible with ext4 user quotas (`usrquota` on `/`) for `<m>-cc` and `<m>-hands`; that is a remount, the admin's call.
A hard cap on volumes needs an XFS filesystem with project quotas under `/var/lib/docker` (a new volume and a migration), not done here.

## The numbers (default profile)

Sized for a CAX31 (8 vCPU, 15577 MiB, 150 GB) with five members, the admin brain and the one shared Ollama.

| service | cpus | ceiling | reservation | pids |
|---|---|---|---|---|
| api | 1.5 | 2560m | 768m | 512 |
| ui | 0.5 | 384m | 128m | 128 |
| nodeos | 0.25 | 256m | 64m | 128 |
| public-chat | 0.5 | 256m | 96m | 128 |
| postgres | 1.0 | 768m | 192m | 256 |
| redis | 0.25 | 128m | 32m | 64 |
| slice (reasoner, jobs) | 1.5 | 2560M (high 2048M) | 256M | 1024 tasks |
| one tenant | 5.5 | 6912M | 1536M | 2240 |
| shared Ollama (admin only) | 6.0 | 5120m | 3072m | 256 |

The api's ceiling is high because it loads the bge-large embedding model in process on its first embed (about 1.8 GB).
The Ollama also gets `OLLAMA_NUM_PARALLEL=2` and `OLLAMA_MAX_LOADED_MODELS=2`.
Per tenant: 3 running jobs, no spend ceiling, 15 GB disk.

Box total with six tenants: reservations 6 x 1536 + 3072 + 1024 host = 13312 MiB of 15577 (85 percent), ceilings 3.06 times the box (bound 4), disk 6 x 15 + 40 shared = 130 of 150 GB.
A seventh tenant still fits (95 percent); an eighth does not, and the check says so.
CPU limits are ceilings, not shares: CPU is compressible and the kernel shares it fairly between busy cgroups, so the sum (33) may exceed 8; one tenant may not pass 75 percent of the box.

## Overrides

Any number, for one run of add-member.sh or the check: `BRAIN_LIMIT_<SERVICE>_CPUS`, `_MEM`, `_MEM_RES`, `_PIDS` (SERVICE is API, UI, NODEOS, PUBLIC_CHAT, POSTGRES, REDIS, OLLAMA), `BRAIN_LIMIT_SLICE_CPUS`, `_MEM_HIGH`, `_MEM`, `_MEM_RES`, `_TASKS`, `BRAIN_LIMIT_JOBS`, `BRAIN_LIMIT_SPEND_EUR`, `BRAIN_LIMIT_DISK_GB`.
The box: `BOX_MEM_MB`, `BOX_CPUS`, `BOX_DISK_GB`, `BOX_HOST_RESERVE_MB`, `BOX_DISK_RESERVE_GB`, `BOX_MAX_SHARE`, `BOX_MAX_CPU_SHARE`, `BOX_MAX_OVERCOMMIT`.

## The check (prints only)

    python3 scripts/member_limits.py check --plan            # every member with the profile: does the box hold it?
    python3 scripts/member_limits.py check --plan --add 1    # and one more member?
    python3 scripts/member_limits.py check                   # as set now: reads each override, slice and limits env

It fails (exit 1) when a tenant has no memory ceiling, CPU limit, process limit or job cap somewhere; when the reservations plus the host reserve pass the box's memory; when one tenant's ceiling passes half the box or its CPU 75 percent; when the ceilings pass 4 times the box; or when the disk quotas plus the shared reserve pass the disk.
The as-set check reads the admin brain's override at `/home/hbar/brain` (`--admin-dir`, or `--no-admin`).
It cannot see limits set in a `.env` (that file holds secrets and is not read); set them in the override.

The other subcommands also only print: `profile`, `override`, `merge <file> [--admin]` (an existing override with the limits merged in, other keys kept, comments dropped), `unit <m|admin> slice|bridge|term|env`, `parent brain|system`, `disk`.

## What these limits do not cover

The shared Ollama has no auth and listens on 127.0.0.1: any local user, every member's hands included, can pull a model into it (disk) or delete one (everyone's answers).
Its memory ceiling stops it from taking the box, but per-member fairness inside it is first come; the api's rate limits are what stands between one member and the queue.
Closing the port to the member users (an `iptables -m owner` rule, or an auth proxy) is a separate change.

The same holds for each member's terminal door (ttyd on 127.0.0.1, port 8100+10n+7). It carries no credential, and Caddy's operator token is never checked by ttyd. So another member's users can open a member's `<m>-cc` shell, with that bridge's env, over loopback (audit 2026-11-13, open; fix and workaround in docs/CC.md, Security shape). NodeOS reads (2026-11-13) and the bridge's tokenless local routes (2026-11-13) are closed to other members.
