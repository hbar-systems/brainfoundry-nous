#!/usr/bin/env bash
# scripts/retrofit_git.sh — Track J2
#
# Convert an rsync-deployed brain into a git checkout, in place.
#
# Brains are deployed by rsync with --exclude='.git', so /home/hbar/brain holds
# the code but is not a git repository — the console Update button and
# `brain update` both fail with "not a git repository". This script turns an
# existing brain directory into a proper checkout of origin/main WITHOUT
# re-downloading the code and WITHOUT touching the working tree, so there is no
# data loss: postgres data, the api_runtime volume, .env, and the personalized
# api/brain_persona.local.md are all left exactly as they are. It only adds a
# .git/ directory and points branch `main` at origin/main.
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
# Idempotent: if the brain is already a git checkout, it exits 0 with no change.
#
# Usage:   bash scripts/retrofit_git.sh [BRAIN_DIR]
#          BRAIN_DIR defaults to the repo root inferred from this script's path
#          (so running it from inside a deployed brain just works).
#
# After running: `git status` is clean and `git pull` updates the brain.

set -euo pipefail

REMOTE_URL="https://github.com/hbar-systems/brainfoundry-nous.git"

# --- locate the brain directory ----------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BRAIN_DIR="${1:-$(cd "${SCRIPT_DIR}/.." && pwd)}"

if [ ! -d "${BRAIN_DIR}" ]; then
  echo "ERROR: brain directory not found: ${BRAIN_DIR}" >&2
  exit 1
fi
cd "${BRAIN_DIR}"
echo "retrofit_git: target brain directory = ${BRAIN_DIR}"

# --- idempotency: already a git checkout? ------------------------------------
if git rev-parse --git-dir >/dev/null 2>&1; then
  echo "retrofit_git: already a git checkout — nothing to do."
  exit 0
fi

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

# --- build the checkout in place ---------------------------------------------
echo "retrofit_git: initializing git repository..."
git init -q
# Force the branch name to `main` regardless of the host's git defaults.
git symbolic-ref HEAD refs/heads/main

if git remote get-url origin >/dev/null 2>&1; then
  git remote set-url origin "${REMOTE_URL}"
else
  git remote add origin "${REMOTE_URL}"
fi

echo "retrofit_git: fetching origin (metadata only — no working-tree download)..."
git fetch -q origin

# Move HEAD + index to origin/main. --mixed leaves every working-tree file
# untouched — the code is already on disk from the rsync deploy.
echo "retrofit_git: pointing main at origin/main (working tree untouched)..."
git reset -q --mixed origin/main
git branch --set-upstream-to=origin/main main >/dev/null 2>&1 || true

# --- report ------------------------------------------------------------------
echo
echo "retrofit_git: done — ${BRAIN_DIR} is now a git checkout of origin/main."
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
