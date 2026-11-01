# update_lock.sh: one update or revert at a time per checkout (2026-11-01).
# Sourced by update_brain.sh and revert_brain.sh after BRAIN_DIR is known.
#
# 2026-10-06: two Updates pressed at once on hbar left brain-ui stuck and the
# console on 502. The lock is a kernel flock on $BRAIN_DIR/.update.lock: the
# same file (same inode) on the host and inside the api container, so the
# Update button, the auto-update loop and a run by hand all see it. The kernel
# drops the lock when the holder exits or dies, so a crashed run never wedges
# the next one. Each checkout has its own file: members on a shared box do not
# block each other.
#
# A second run exits 75 (EX_TEMPFAIL) before touching git or docker. If the
# lock cannot be taken at all (no flock, unwritable dir), the run goes on as
# before with a warning: the guard must never be the reason an update fails.

UPDATE_LOCK_BUSY=75

take_update_lock() {
    local what="$1" lock="$BRAIN_DIR/.update.lock"
    if ! command -v flock >/dev/null 2>&1; then
        echo "!  no flock on this system: running without the one-at-a-time guard"
        return 0
    fi
    # Open read-only: flock needs no write access, so a lock file root created
    # from the container still works for the host user, and vice versa.
    # Created world-readable whatever the caller's umask (a member checkout runs under
    # 027): an empty file, and every launcher must be able to open it.
    [ -e "$lock" ] || ( umask 022; : > "$lock" ) 2>/dev/null || true
    if ! { exec 9<"$lock"; } 2>/dev/null; then
        echo "!  cannot open $lock: running without the one-at-a-time guard"
        return 0
    fi
    if ! flock -n 9; then
        echo "✗ another update or revert is already running on $BRAIN_DIR; this $what stops here and changes nothing."
        echo "  Wait for it to finish, then look at the Update page."
        exit "$UPDATE_LOCK_BUSY"
    fi
}
