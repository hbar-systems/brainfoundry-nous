#!/usr/bin/env bash
set -e

PROJECT_ROOT="${PROJECT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)}"
cd "$PROJECT_ROOT"

if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate

echo "✅ In project and venv."
echo "pwd: $(pwd)"
echo "venv: $VIRTUAL_ENV"
