#!/usr/bin/env bash
# scripts/cc/install-codex.sh — opt-in: the Codex CLI for the hands user (the Codex seat).
# Created: 2026-10-15. Not run by install.sh; run it once, by hand, when you want the seat.
#
# Run ON the brain's server as the brain user (needs sudo to act as the hands), from the brain repo:
#     bash scripts/cc/install-codex.sh
# What it does: installs OpenAI's Codex CLI, pinned to CODEX_VERSION, from npm into the hands
# user's own ~/.local (no system-wide install, no root-owned files), and prints its version and
# sign-in state. It does not sign in; that is the console's "Sign in with ChatGPT" (or, on the box:
# sudo -u <hands> -H codex login --device-auth). It touches no .env and no credentials.
# Needs node >= 16 and npm on the box (apt install nodejs npm, if missing).
#
# Rollback: sudo -u <hands> -H npm uninstall -g --prefix ~<hands>/.local @openai/codex
set -euo pipefail

CODEX_VERSION=${CODEX_VERSION:-0.162.1}   # keep in step with PINNED_VERSION in scripts/cc/cc_codex.py
BRIDGE_USER=$(grep -oP '^User=\K.*' /etc/systemd/system/cc-bridge.service 2>/dev/null || id -un)
BRIDGE_HOME=$(eval echo "~$BRIDGE_USER")
HANDS_USER=${HANDS_USER:-$(sudo grep -oP '^CC_HANDS_USER=\K.*' "$BRIDGE_HOME/.cc-bridge/env" 2>/dev/null || true)}
HANDS_USER=${HANDS_USER:-$BRIDGE_USER}
HANDS_HOME=$(eval echo "~$HANDS_USER")
AS_HANDS=""; [ "$HANDS_USER" != "$(id -un)" ] && AS_HANDS="sudo -u $HANDS_USER -H"

command -v npm >/dev/null || { echo "npm is missing: sudo apt-get install -y nodejs npm, then run this again"; exit 1; }
NODE_MAJOR=$(node -p 'process.versions.node.split(".")[0]' 2>/dev/null || echo 0)
[ "$NODE_MAJOR" -ge 16 ] || { echo "node >= 16 needed (found $(node --version 2>/dev/null || echo none))"; exit 1; }

echo "== Codex CLI $CODEX_VERSION for $HANDS_USER (into $HANDS_HOME/.local)"
$AS_HANDS env HOME="$HANDS_HOME" npm install -g --no-fund --no-audit --prefix "$HANDS_HOME/.local" "@openai/codex@$CODEX_VERSION"
$AS_HANDS env HOME="$HANDS_HOME" PATH="$HANDS_HOME/.local/bin:/usr/local/bin:/usr/bin:/bin" "$HANDS_HOME/.local/bin/codex" --version

# The seat runs every command in Codex's own read-only sandbox (bubblewrap). On kernels that
# restrict unprivileged user namespaces (Ubuntu 24.04: kernel.apparmor_restrict_unprivileged_userns=1)
# the sandbox may fail to start; then Codex can run no command at all and answers from the prompt
# alone. That is closed, not open; this line only says which one you have.
if $AS_HANDS env HOME="$HANDS_HOME" PATH="$HANDS_HOME/.local/bin:/usr/bin:/bin" "$HANDS_HOME/.local/bin/codex" sandbox -- true >/dev/null 2>&1; then
    echo "sandbox: works (Codex can read files on this box, read-only)"
else
    echo "sandbox: does not start here (Codex cannot run commands; it answers from memory and the prompt only)"
fi

# Signed in or not: the exit code only, never the CLI's own words.
if $AS_HANDS env HOME="$HANDS_HOME" PATH="$HANDS_HOME/.local/bin:/usr/bin:/bin" "$HANDS_HOME/.local/bin/codex" login status >/dev/null 2>&1; then
    echo "sign-in: signed in"
else
    echo "sign-in: not yet. In the console: Sign in with ChatGPT (opens OpenAI's device-code flow)."
    echo "  First turn on ChatGPT > Settings > Security > Device code authorization."
fi
