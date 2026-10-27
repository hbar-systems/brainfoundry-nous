#!/usr/bin/env bash
# test-gate.sh: run the whole tests/ suite and say GREEN or RED in one line (2026-10-27).
# Exit 0 green, 1 red. For the steward before a push, or as a pre-commit hook:
#   ln -s ../../scripts/test-gate.sh .git/hooks/pre-commit
# The python needs requirements.txt plus pytest; sentence_transformers is optional (tests/conftest.py).
#   TEST_PYTHON=/tmp/bfvenv/bin/python bash scripts/test-gate.sh
set -u
cd "$(dirname "$(readlink -f "$0")")/.." || exit 1
PY="${TEST_PYTHON:-python3}"
out="$("$PY" -m pytest tests -q -p no:cacheprovider -W ignore 2>&1)"
rc=$?
last="$(printf '%s\n' "$out" | tail -1)"
if [ "$rc" -eq 0 ]; then
  echo "test-gate: GREEN $last"
  exit 0
fi
echo "test-gate: RED $last"
printf '%s\n' "$out" | grep -E '^(FAILED|ERROR) ' | head -40
exit 1
