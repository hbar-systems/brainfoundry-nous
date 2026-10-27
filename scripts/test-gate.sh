#!/usr/bin/env bash
# test-gate.sh: run the whole tests/ suite and say GREEN or RED in one line (2026-10-27).
# Exit 0 green, 1 red. For the steward before a push, or as a pre-commit hook:
#   ln -s ../../scripts/test-gate.sh .git/hooks/pre-commit
# The python needs requirements.txt plus pytest; sentence_transformers is optional (tests/conftest.py).
# Default: the durable venv /home/hands/.local/venvs/nous-tests when it exists (2026-10-27), else python3.
# It is requirements.txt + api/requirements.txt without sentence-transformers (that pulls torch, ~3 GB),
# plus pytest and permitd; to rebuild it:
#   cat requirements.txt api/requirements.txt | grep -vi '^sentence-transformers' > /tmp/req.txt
#   python3 -m venv ~/.local/venvs/nous-tests && ~/.local/venvs/nous-tests/bin/pip install --no-cache-dir -r /tmp/req.txt pytest permitd
#   TEST_PYTHON=/other/venv/bin/python bash scripts/test-gate.sh     another python
set -u
cd "$(dirname "$(readlink -f "$0")")/.." || exit 1
VENV_PY=/home/hands/.local/venvs/nous-tests/bin/python
if [ -z "${TEST_PYTHON:-}" ] && [ -x "$VENV_PY" ]; then TEST_PYTHON=$VENV_PY; fi
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
