# The kill switch

Created 2026-10-25. hbar: "A kill switch you can press from the phone."

One file stops the hands from starting anything new. Nothing else changes: the brain still answers,
permits still work, running jobs keep running unless you say otherwise.

## The file

`/home/hands/.cc-bridge/HALT` — the hands' home (on a single-user box, the bridge user's home; it is
always `~/.cc-bridge/HALT` of whoever runs cc-job). The hands user writes it; the bridge user reads it
(it is in the `hands` group and the directory is 755). First line is the reason; a second line says
when and by whom. An empty file is still a halt.

Writer: only `cc-job halt` / `cc-job resume` (scripts/cc/cc-job.py, installed as `~/.local/bin/cc-job`;
install.sh now also copies `scripts/cc/cc_halt.py` beside it). The phone and the page go through the
same two commands, so every press is one line in `/home/hands/.cc-bridge/halt.log`.

## What honours it

While the file exists:

- `cc-job run` is refused by the bridge (`POST /jobs/start` answers 409) and prints `HALT: <reason>`.
  Every standing agent's job goes through cc-job, so they stop too.
- The tick (`CC_TICK_CMD`, memo dispatch every 30 min) is skipped: the journal says `tick skipped: HALT: ...`.
- Standing agents: the bridge's agents loop waits, and `cc_agents.py tick` / `cc_agents.py run` answer
  `{"ok": false, "error": "HALT: ..."}` themselves (so Run now on the Agents page is refused as well).
- `/cc/health` carries `"halt": "HALT: <reason>"` (or `null`).

Not honoured, on purpose: the chat (a turn you type still runs; the Agent tool inside a turn is the
reasoner's own, not a cc-job), and the permit gate (cards still ask and still work).

## The three commands (as the hands user, or from the console chat)

    cc-job halt "reason"          write the file; running jobs are left alone
    cc-job halt "reason" --kill   also SIGTERM the process group of every running cc-job
                                  (jobs are tracked in ~/out/jobs/jobs.json with their pid; the bridge
                                  starts each in its own session; a pid the kernel reused is skipped)
    cc-job halt --status          halted or not, budget halts, running jobs; exit 3 while halted
    cc-job resume                 remove the file

## From the phone

In the owner's Telegram chat with the brain's bot (the bridge's lane, `CC_TELEGRAM_TOKEN`, live on hbar),
send the single word

    halt
    resume

exact, any case, nothing else in the message. Owner-only: a stranger's chat gets "This brain is
private." before the word is read. The bridge runs `cc-job halt "from the phone (telegram)"` /
`cc-job resume` as the hands and sends you cc-job's answer. The api container's Telegram
(`api/integrations/telegram.py`) is a read-and-answer lane inside the container and cannot see the hands'
filesystem; it is not wired to the switch and does not need to be.

## Budget HALT

`ops/finance/budgets.tsv` in the world (`CC_WORLD_DIR`), written every 10 min by the finance thread, has
columns `post | weekly_cap_eur | spent_this_week_eur | state`. When `state` reads `HALT-<post>`, the bridge
refuses a job whose title starts with `<post>:` (case-insensitive) with
`HALT: budget for <post> is spent this week (HALT-<post> in ops/finance/budgets.tsv)`. Tolerant: no file,
no `state` column, or no matching title means no budget halt. Only titled jobs are matched; a job with no
post prefix is not a post's spend. On 2026-10-25 the file already says HALT for i-hands, j2-intelligence
and v-doors (caps PROPOSED, hbar rules them).

## What it does not do

- Does not stop the brain's chat or the console turn you are in.
- Does not touch permits, the posture, or the permission settings.
- Does not kill running jobs unless `--kill` is given; never kills anything that is not a cc-job.
- Does not stop a job already running under another brain or box.

## Going live

The bridge on hbar runs `/home/hbar/brain/scripts/cc/cc-bridge.py`; this change is in the nous repo and
reaches the box with push + Update (`sudo bash /home/hbar/brain/scripts/update_brain.sh`, then the
bridge restarts). `install.sh` re-copies `cc-job` and `cc_halt.py` into `/home/hands/.local/bin/`;
until then the installed cc-job is the old one and `cc-job halt` on the box is not yet a command. No
mount or env change is needed: the bridge lane already reaches Telegram and the hands' directory.

## Tests

`tests/test_cc_halt.py` (7 tests): file set/read/clear and the log, empty reason, budgets.tsv parsing
and title matching, refusal order, kill by process group (fake killer: finished, reused-pid, not-ours
and gone pids skipped), cc_agents refusal while halted, cc-job halt/status/run-refusal/--kill/resume.

    /tmp/pt/bin/python -m pytest tests/test_cc_halt.py tests/test_cc_agents.py tests/test_cc_extras.py tests/test_cc_bridge.py -q
    1 failed, 115 passed      (the failure, test_cc_agents::test_levels_shape_permissions, fails on HEAD too)

Manual, 2026-10-25, temp HOME, the repo's cc-job:

    $ cc-job halt --status
    not halted (no HALT file)
    budget halts: i-hands (HALT-i-hands), j2-intelligence (HALT-j2-intelligence), v-doors (HALT-v-doors)
    running jobs: 0
    $ cc-job halt "phone test"
    HALT: phone test
    no new job, tick or agent starts until: cc-job resume
    $ cc-job halt --status            # rc=3
    HALT: phone test
    $ cc-job resume
    resumed: new jobs, the tick and agents may start again
    $ cat ~/.cc-bridge/halt.log
    2026-10-25T17:50:17Z halt by hands: phone test
    2026-10-25T17:50:18Z resume by hands: cleared
