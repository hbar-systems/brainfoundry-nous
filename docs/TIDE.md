# Tide: the brain updates itself at a quiet moment

Created 2026-11-27 (AUTO-UPDATE-1 "Tide").

hbar, 2026-11-27: "we should have a system now does update automatically in optimal moments of the workflow so for example of all systems are going and then update won't harm any of the or interfere in any of these autonomous versions and I'm clearly not interacting directly at this time then it should make an update."

## What it does

Every five minutes a root timer on the box (`brain-tide.timer`) fetches origin/main and asks the bridge one question: is this a quiet moment?
When the answer is yes, it runs the same Update the button runs: `scripts/update_brain.sh` of the checkout, as the checkout's owner, with the same checks, backup and lock.
Before the update, a line goes to the central thread and to Telegram: `updating now: <n> commits: <first lines>`.
After it: `updated to <sha>, healthy`, or the failure and which version runs.
A commit whose update failed is not tried again until a newer commit arrives.

Off by default in the template.
It turns on for a brain only when its owner presses "Turn on" on `/update`.
Member brains on a shared box are left alone: their bridge refuses the switch and the installer refuses their bridge.

## The rule (scripts/cc/cc_tide.py, `quiet()`)

Yes only when all of these hold. Otherwise the first reason, in plain words, is the answer shown on `/update`.

1. The switch is on and the brain is not a member's.
2. The HALT file is absent (the hands' and the owner's).
3. origin/main is ahead of the checkout.
4. No update is running, and the latest commit is not the one whose update failed.
5. No automatic update began in the last hour.
6. No turn is answering in any thread.
7. No card is waiting for his press.
8. No upload or recording is coming in (a request in flight, or a resumable upload's piece in the last 10 minutes).
9. His last message or press anywhere (console, Telegram) and the terminal pane's last activity are older than 20 minutes.

Running cc-jobs and standing agents do not block (see below). The answer still says how many run on.

"His touch" is a list of POST routes only a person sends: `/chat`, card presses, logged presses, `/threads/<id>/say`, side notes, uploads, recordings, `/update`, the switch, restarts. Telegram messages and button presses from the owner's chat count too. The page's own timers do not, so a tab left open cannot keep the brain from ever being quiet.

## What dies in an update (measured 2026-11-27)

| What | Effect | So the rule |
|---|---|---|
| A turn in flight | An update that changes `scripts/cc/install.sh` reruns it (`cc-install-watch`), which restarts `cc-bridge` and `claude-tab` at once; the reasoner's pipe to the bridge is cut and the answer is lost. A change to `cc-bridge.py` alone restarts the bridge only when idle. | waits for no turn |
| A card | It lives inside the turn waiting for it. | waits for no card |
| The terminal pane | The same rerun restarts `claude-tab` (KillMode=control-group: the tmux session and what runs in it). | waits until the terminal has been idle 20 min |
| An upload | The request is cut. | waits for none in flight |
| The api, 30 to 60 s | Recreated on its new image; memory calls fail in that window. | (nothing waits on it) |
| cc-jobs, standing agents | **Survive.** `cc-bridge.service` has `KillMode=process`: only the bridge's own process is stopped, the jobs stay in the unit's group and write their rc to a file that the next bridge reads. | do not block |

Proof that jobs survive, from `/home/hands/out/jobs/jobs.json` and the units' timestamps:

- SEAT-3 (`J1795466731615`, a `claude -p` build) ran 20:45 to 23:10 UTC on 2026-11-23, through the hard restart of `cc-bridge` and `claude-tab` by `cc-install-watch` at 22:30:35 to 22:30:49, and ended rc=0.
- METRICS-1 preview (`J1795651533706`) ran from 2026-11-26 00:05 through the bridge restarts at 04:03 (`cc-bridge-watch`) and 06:30:50, and was stopped by hand on 11-27 (rc=143).

`JOBS_BLOCK = True` in `cc_tide.py` puts jobs back in the rule.

## The root step

The update needs root (hbar's checkout is root's; the card today is `sudo bash scripts/update_brain.sh`).
Nothing new is given to the bridge or the hands: no sudoers line, no new verb.

- `scripts/tide/brain-tide.sh`, installed as `/usr/local/sbin/brain-tide` (root 755, a fixed copy).
- `brain-tide.service` (oneshot, its own unit outside the bridge's group, so a bridge restart during the update does not stop it) and `brain-tide.timer` (every five minutes).
- The runner believes the answer only from the socket on `127.0.0.1:<CC_PORT>` that belongs to the bridge's user. The bridge answers `/cc/autoupdate/quiet`, `/begin` and `/end` only to uid 0 on loopback with no proxy header.
- At `begin` the bridge asks the rule again under its lock and checks the commits match; only then the line goes out and the run is recorded.
- The answer gates the moment only. What runs is fixed: the checkout's `scripts/update_brain.sh`, after checks that refuse host-run files not the owner's or root's, world-writable ones, group-writable ones (except by an empty root group), symlinks, git hooks of others, and local changes to tracked `scripts/` or `docker-compose.yml`. The checks run once more right before the script.
- Output: `/var/lib/brain-tide/update.log` (the script's), `tide.log` (each look and its answer), `last.json` (the last run).
- If the bridge is restarting when the update ends, the runner retries the report for ten minutes; a run that never reports is closed as "never reported back" after 40 minutes.

### Install once (his hands)

In the console's terminal pane, as hbar:

```
[ "$(hostname)" = hbar ] && cd /home/hbar/brain && sudo bash scripts/tide/install-tide.sh --dry-run
[ "$(hostname)" = hbar ] && cd /home/hbar/brain && sudo bash scripts/tide/install-tide.sh --apply
```

The first prints every action and changes nothing. The second installs, starts the timer and asks once (prints the answer; never updates).
Then on `/update` press "Turn on". Off again: the same button. Remove the timer: `sudo bash scripts/tide/install-tide.sh --remove`.
Rerun `--apply` after an Update that changes `scripts/tide/`.

## The page

`/update` shows one line above the daily switch: `updates itself at quiet moments: on/off` with its button, the next check's answer in words (`waiting: 2 conversations answering`), whether the box timer is asking, and the last three automatic updates.

## Relation to the daily switch

"Keep this brain updated" (2026-09-23) still runs the update once a day at an hour, from inside the api container, without looking at turns, cards or his presence. Use one or the other. With the Tide on, turn the daily switch off.
