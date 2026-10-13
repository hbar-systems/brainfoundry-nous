#!/usr/bin/env bash
# scripts/cc/safe-pull.sh <repo>   Created 2026-10-13.
# The one way a thread brings a repository up to date before editing, when several threads share
# one checkout (hbar runs three in parallel). Never rebases, never resets, never stashes: a rebase
# rewrites hashes that other threads, the done box and the steward have already recorded, and it
# rewrites the working tree under threads that are mid-edit.
#   only ahead (own unpushed commits)  -> nothing to pull, exit 0
#   only behind                        -> fast-forward; refused if it would touch a dirty file, exit 1
#   ahead and behind                   -> a normal merge; on any conflict, abort, exit 1
# Holds the same lock as world-keep.sh, so no two git updates of the world run at once.
set -u
repo="${1:-.}"
cd "$repo" 2>/dev/null || { echo "safe-pull: no such repo: $repo"; exit 1; }
git rev-parse --git-dir >/dev/null 2>&1 || { echo "safe-pull: not a git repo: $repo"; exit 1; }
mkdir -p "$HOME/.local/state"
exec 9>"$HOME/.local/state/world-keep.lock"
flock -w 120 9 || { echo "safe-pull: another update holds the lock for 2 min; try again"; exit 1; }
git fetch -q 2>/dev/null || { echo "safe-pull: fetch failed (offline?); not pulled"; exit 1; }
git rev-parse -q --verify '@{u}' >/dev/null || { echo "safe-pull: no upstream; nothing to pull"; exit 0; }
[ -e "$(git rev-parse --git-dir)/MERGE_HEAD" ] && { echo "safe-pull: a merge is already in progress here; stop and tell the person"; exit 1; }
read -r ahead behind < <(git rev-list --left-right --count 'HEAD...@{u}')
if [ "$behind" = 0 ]; then echo "safe-pull: up to date ($ahead local commit(s) not yet pushed)"; exit 0; fi
if [ "$ahead" = 0 ]; then
  git merge -q --ff-only '@{u}' && { echo "safe-pull: fast-forwarded $behind"; exit 0; }
  echo "safe-pull: behind $behind, not pulled: it would overwrite a file another thread is editing"; exit 1
fi
if git merge -q --no-edit '@{u}'; then echo "safe-pull: merged $behind from origin under $ahead local commit(s)"; exit 0; fi
git merge --abort 2>/dev/null
echo "safe-pull: ahead $ahead and behind $behind, merge would conflict; aborted, nothing changed"; exit 1
