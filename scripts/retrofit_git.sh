#!/usr/bin/env bash
# scripts/retrofit_git.sh — Track J2
#
# Make a brain directory a git checkout that tracks origin/main, in place.
#
# Brains are rsync-deployed with --exclude='.git', so /home/hbar/brain ends up
# in one of two broken states:
#   (a) no .git at all — the console Update button and `brain update` fail
#       with "not a git repository";
#   (b) a STALE .git — the brain was git-cloned once, then rsync-deployed over
#       ever since (rsync skips .git), so HEAD is frozen at an ancient commit
#       while the working tree is current. `git status` shows everything as
#       modified and `git pull` cannot work.
# This script fixes both: it points branch `main` at origin/main WITHOUT
# touching the working tree, so there is no data loss — postgres data, the
# api_runtime volume, .env, and the personalized api/brain_persona.local.md
# are all left exactly as they are. `git reset --mixed` moves only HEAD + the
# index; the code on disk (already current from rsync) is never rewritten.
#
# ORDER — this matters:
#   1. Ship Track J1 and PUSH it to origin/main on GitHub.
#   2. Redeploy each brain via rsync. J1's startup migration moves an
#      already-personalized persona into the gitignored brain_persona.local.md.
#   3. THEN run this script on each brain host.
# Running this before origin/main carries J1 would track the personalized
# persona, and a later `git pull` would overwrite the brain's identity — the
# exact failure J1 exists to prevent. This script refuses to run unless the J1
# split is present (api/brain_persona.template.md must exist).
#
# Idempotent: running it on a brain whose `main` already points at origin/main
# changes nothing. Running it on a no-.git or stale-.git brain converges it.
#
# Usage:   bash scripts/retrofit_git.sh [BRAIN_DIR]
#          BRAIN_DIR defaults to the repo root inferred from this script's path
#          (so running it from inside a deployed brain just works).
#
# After running: `git status` is clean and `git pull` updates the brain.

set -euo pipefail

REMOTE_URL="https://github.com/hbar-systems/brainfoundry-nous.git"

# --- locate the brain directory ----------------------------------------------
# Resolve to a physical (symlink-free) path so the --show-toplevel guard below
# compares cleanly — `git rev-parse --show-toplevel` always returns a physical
# path, and parents like /var or /tmp are often symlinks.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
BRAIN_DIR_ARG="${1:-${SCRIPT_DIR}/..}"

if [ ! -d "${BRAIN_DIR_ARG}" ]; then
  echo "ERROR: brain directory not found: ${BRAIN_DIR_ARG}" >&2
  exit 1
fi
cd "${BRAIN_DIR_ARG}"
BRAIN_DIR="$(pwd -P)"
echo "retrofit_git: target brain directory = ${BRAIN_DIR}"

# --- precondition: Track J1 must be deployed ---------------------------------
if [ ! -f api/brain_persona.template.md ]; then
  echo "ERROR: api/brain_persona.template.md not found." >&2
  echo "       Track J1 is not deployed to this brain. Deploy J1 first —" >&2
  echo "       retrofitting a pre-J1 brain would track the personalized" >&2
  echo "       persona, and a later 'git pull' would erase the brain's" >&2
  echo "       identity. Aborting." >&2
  exit 1
fi

# --- warn if a pre-J1 legacy persona file is still present -------------------
if [ -f api/brain_persona.md ]; then
  echo "WARNING: api/brain_persona.md (pre-J1 legacy persona) is still present." >&2
  echo "         J1's startup migration should have moved it into" >&2
  echo "         api/brain_persona.local.md and removed it. Restart the api" >&2
  echo "         container ('docker compose up -d --build') to complete the" >&2
  echo "         migration. The file is gitignored, so this is non-fatal." >&2
fi

# --- is there already a git checkout rooted exactly here? --------------------
# (`--show-toplevel` guards against git walking up to a parent repository.)
IS_REPO=no
if git rev-parse --git-dir >/dev/null 2>&1 \
   && [ "$(git rev-parse --show-toplevel 2>/dev/null || true)" = "${BRAIN_DIR}" ]; then
  IS_REPO=yes
fi

if [ "${IS_REPO}" = no ]; then
  echo "retrofit_git: no git repository here — initializing..."
  git init -q
else
  echo "retrofit_git: existing git repository found — re-pointing it at origin/main..."
fi

# Force HEAD onto branch `main`. This rewrites only the .git/HEAD pointer — it
# never touches the index or the working tree. Handles a fresh init (unborn
# main), a stale checkout on main, and a checkout on some other/detached ref.
git symbolic-ref HEAD refs/heads/main

# --- ensure the origin remote -------------------------------------------------
if git remote get-url origin >/dev/null 2>&1; then
  git remote set-url origin "${REMOTE_URL}"
else
  git remote add origin "${REMOTE_URL}"
fi

echo "retrofit_git: fetching origin (metadata only — no working-tree download)..."
git fetch -q origin

# --- converge branch main onto origin/main -----------------------------------
ORIGIN_MAIN="$(git rev-parse origin/main)"
HEAD_NOW="$(git rev-parse -q --verify HEAD 2>/dev/null || true)"
if [ "${HEAD_NOW}" = "${ORIGIN_MAIN}" ]; then
  echo "retrofit_git: branch main is already at origin/main — nothing to move."
else
  # --mixed moves HEAD + index to origin/main; every working-tree file is left
  # untouched (the code is already on disk from the rsync deploy).
  echo "retrofit_git: pointing main at origin/main (working tree untouched)..."
  git reset -q --mixed origin/main
fi
git branch --set-upstream-to=origin/main main >/dev/null 2>&1 || true

# --- report -------------------------------------------------------------------
echo
echo "retrofit_git: done — ${BRAIN_DIR} is a git checkout tracking origin/main."
git --no-pager log --oneline -1 origin/main 2>/dev/null | sed 's/^/  origin\/main is at: /' || true
echo
DIRTY="$(git status --porcelain | wc -l | tr -d ' ')"
if [ "${DIRTY}" = "0" ]; then
  echo "  git status: clean. 'git pull' will now update this brain."
else
  echo "  git status: ${DIRTY} path(s) differ from origin/main —"
  git status --short | sed 's/^/    /'
  echo
  echo "  If these are runtime/ignored files, add them to .gitignore."
  echo "  If they are tracked source files, origin/main is BEHIND the code"
  echo "  deployed to this brain — push the deployed commit to origin/main"
  echo "  and the divergence resolves."
fi
