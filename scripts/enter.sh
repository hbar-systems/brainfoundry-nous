#!/usr/bin/env bash
set -e

PROJECT_ROOT="/Users/hbar/dev/hbar-brain-slm"

cd "$PROJECT_ROOT" || { echo "Missing: $PROJECT_ROOT"; exit 1; }

# create venv if it doesn't exist (no extra installs)
if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi

# activate
# shellcheck disable=SC1091
source .venv/bin/activate

echo "✅ In project and venv."
echo "pwd: $(pwd)"
echo "venv: $VIRTUAL_ENV"
echo
echo "Next: say 'next' and I’ll give you the Docker start script."
