#!/bin/bash
#
# vault-setup.sh — one-time setup of the private vault (2026-10-15).
#
# RUN THIS AS THE BRAIN'S OWNER (e.g. hbar), on the brain host, from the brain
# checkout. Not as hands or cc, not from an agent: the point of the vault is
# that the Unix users the closed reasoners run as cannot read it.
#
# What it does, in order, and stops at the first thing that fails:
#   1. creates the vault directory (default /home/<owner>/vault), owned by the
#      owner, mode 700, no extra ACL entries;
#   2. checks that none of the closed users (hands, cc) is in the docker group
#      (docker = root on this host, so a member could read the vault through a
#      container) — a failure here means the wall cannot hold;
#   3. adds the read-only mount to docker-compose.override.yml (creates the
#      file if absent, edits the api block if present; backup kept, and the
#      edit is undone if `docker compose config` rejects it):
#          services.api.volumes:     - <vault>:/vault:ro
#          services.api.environment: BRAIN_VAULT_DIR: <vault>
#   4. verifies the wall: `sudo -u hands ls <vault>` and `sudo -u cc ls <vault>`
#      must fail, and neither may read a probe file written inside it.
#
# It does not restart anything. After it passes:
#   docker compose up -d api          # recreate the api with the mount
#   curl -s -H "X-API-Key: $KEY" http://127.0.0.1:8010/vault   # mounted: true
#
# USAGE
#   scripts/vault-setup.sh [VAULT_DIR]
#   env: BRAIN_OWNER (default: you), BRAIN_DIR (default: this checkout),
#        VAULT_CLOSED_USERS (default: "hands cc"), BRAIN_VAULT_DIR (same as arg)
#   scripts/vault-setup.sh --check [VAULT_DIR]   only step 2 and step 4
#
# Needs sudo for the checks (sudo -u <user>) and, when the brain checkout is
# root-owned, for writing the override file.
set -euo pipefail

CHECK_ONLY=0
if [ "${1:-}" = "--check" ]; then CHECK_ONLY=1; shift; fi

ME="$(id -un)"
OWNER="${BRAIN_OWNER:-$ME}"
BRAIN_DIR="${BRAIN_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
VAULT_DIR="${1:-${BRAIN_VAULT_DIR:-/home/$OWNER/vault}}"
CLOSED_USERS="${VAULT_CLOSED_USERS:-hands cc}"
OVERRIDE="$BRAIN_DIR/docker-compose.override.yml"

say()  { printf 'vault-setup: %s\n' "$*"; }
die()  { printf 'vault-setup: FAIL: %s\n' "$*" >&2; exit 1; }

[ "$ME" = "root" ] && [ -z "${BRAIN_OWNER:-}" ] && die "run as the brain's owner, or set BRAIN_OWNER when running as root"
for u in $CLOSED_USERS; do
  [ "$ME" = "$u" ] && die "this is run by the owner, not by $u"
  [ "$OWNER" = "$u" ] && die "the owner cannot be a closed user ($u)"
done
case "$VAULT_DIR" in
  /*) ;;
  *) die "VAULT_DIR must be an absolute path: $VAULT_DIR" ;;
esac
case "$VAULT_DIR" in
  *[[:space:]:]*) die "VAULT_DIR may not contain spaces or colons: $VAULT_DIR" ;;
esac
id "$OWNER" >/dev/null 2>&1 || die "no such user: $OWNER"

SUDO=""
[ "$ME" != "root" ] && SUDO="sudo"
as_owner() { if [ "$ME" = "$OWNER" ]; then "$@"; else $SUDO -u "$OWNER" "$@"; fi; }

# ── 1. the directory ─────────────────────────────────────────────────────────
if [ "$CHECK_ONLY" = "0" ]; then
  if [ -e "$VAULT_DIR" ] && [ ! -d "$VAULT_DIR" ]; then die "$VAULT_DIR exists and is not a directory"; fi
  if [ -L "$VAULT_DIR" ]; then die "$VAULT_DIR is a symlink; use the real path"; fi
  if [ ! -d "$VAULT_DIR" ]; then
    as_owner mkdir -p "$VAULT_DIR"
    say "created $VAULT_DIR"
  fi
  cur_owner="$(stat -c %U "$VAULT_DIR")"
  if [ "$cur_owner" != "$OWNER" ]; then
    $SUDO chown "$OWNER:$(id -gn "$OWNER")" "$VAULT_DIR"
  fi
  as_owner chmod 700 "$VAULT_DIR"
  if command -v setfacl >/dev/null 2>&1; then
    as_owner setfacl -b "$VAULT_DIR" 2>/dev/null || true
  fi
  say "$VAULT_DIR: $(stat -c '%A %U:%G' "$VAULT_DIR")"
fi
[ -d "$VAULT_DIR" ] || die "$VAULT_DIR does not exist (run without --check first)"
mode="$(stat -c %a "$VAULT_DIR")"
[ "$mode" = "700" ] || die "$VAULT_DIR is mode $mode, expected 700"
[ "$(stat -c %U "$VAULT_DIR")" = "$OWNER" ] || die "$VAULT_DIR is not owned by $OWNER"

# ── 2. no closed user may drive docker ──────────────────────────────────────
for u in $CLOSED_USERS; do
  if ! id "$u" >/dev/null 2>&1; then say "user $u does not exist here (nothing to wall off)"; continue; fi
  if id -nG "$u" | tr ' ' '\n' | grep -qx docker; then
    die "$u is in the docker group; docker is root on this host, so $u could read the vault through a container. Remove it: sudo gpasswd -d $u docker"
  fi
  if [ -S /var/run/docker.sock ] && sudo -n -u "$u" test -w /var/run/docker.sock 2>/dev/null; then
    die "$u can write /var/run/docker.sock; the wall cannot hold"
  fi
done
say "no closed user can drive docker"

# ── 3. the read-only mount in docker-compose.override.yml ────────────────────
if [ "$CHECK_ONLY" = "0" ]; then
  W=""
  if [ -e "$OVERRIDE" ]; then [ -w "$OVERRIDE" ] || W="$SUDO"; else [ -w "$BRAIN_DIR" ] || W="$SUDO"; fi
  if [ -e "$OVERRIDE" ] && grep -q ':/vault:ro' "$OVERRIDE"; then
    say "$OVERRIDE already mounts the vault"
  else
    TMP="$(mktemp)"
    trap 'rm -f "$TMP"' EXIT
    VAULT_DIR="$VAULT_DIR" OVERRIDE="$OVERRIDE" python3 - "$TMP" <<'PY'
import os, sys
vault, path, out = os.environ["VAULT_DIR"], os.environ["OVERRIDE"], sys.argv[1]
mount = f"      - {vault}:/vault:ro"
env_map = f"      BRAIN_VAULT_DIR: {vault}"
env_list = f"      - BRAIN_VAULT_DIR={vault}"
lines = open(path).read().splitlines() if os.path.exists(path) else []
if not lines:
    lines = ["# docker-compose.override.yml (gitignored). Vault mount added by scripts/vault-setup.sh."]
def indent(l):
    return len(l) - len(l.lstrip(" "))
def block_end(start, level):
    """first line after `start` whose indent is <= level (ignoring blanks/comments)"""
    j = start + 1
    while j < len(lines):
        l = lines[j]
        if l.strip() and not l.lstrip().startswith("#") and indent(l) <= level:
            break
        j += 1
    return j
svc = next((i for i, l in enumerate(lines) if l.rstrip() == "services:"), None)
if svc is None:
    lines += ["services:", "  api:", "    volumes:", mount, "    environment:", env_map]
else:
    end = block_end(svc, 0)
    api = next((i for i in range(svc + 1, end) if lines[i].rstrip() == "  api:"), None)
    if api is None:
        lines[end:end] = ["  api:", "    volumes:", mount, "    environment:", env_map]
    else:
        aend = block_end(api, 2)
        vol = next((i for i in range(api + 1, aend) if lines[i].rstrip() == "    volumes:"), None)
        if vol is None:
            lines[api + 1:api + 1] = ["    volumes:", mount]
        else:
            lines[vol + 1:vol + 1] = [mount]
        aend = block_end(api, 2)
        env = next((i for i in range(api + 1, aend) if lines[i].rstrip() == "    environment:"), None)
        if env is None:
            lines[aend:aend] = ["    environment:", env_map]
        else:
            nxt = lines[env + 1] if env + 1 < len(lines) else ""
            lines[env + 1:env + 1] = [env_list if nxt.lstrip().startswith("- ") else env_map]
open(out, "w").write("\n".join(lines) + "\n")
PY
    if [ -e "$OVERRIDE" ]; then
      BACKUP="$OVERRIDE.bak-vault-$(date -u +%Y%m%dT%H%M%SZ)"
      $W cp -p "$OVERRIDE" "$BACKUP"
      say "backup: $BACKUP"
    fi
    $W cp "$TMP" "$OVERRIDE"
    if ! (cd "$BRAIN_DIR" && docker compose config -q); then
      if [ -n "${BACKUP:-}" ]; then $W cp -p "$BACKUP" "$OVERRIDE"; else $W rm -f "$OVERRIDE"; fi
      die "docker compose rejected the edited override; restored it. Add by hand under services.api:  volumes: - $VAULT_DIR:/vault:ro"
    fi
    say "$OVERRIDE mounts $VAULT_DIR at /vault (read-only)"
  fi
fi

# ── 4. the wall ──────────────────────────────────────────────────────────────
PROBE="$VAULT_DIR/.wall-check"
as_owner sh -c "umask 077; printf 'wall check %s\n' \"\$(date -u +%FT%TZ)\" > '$PROBE'"
fail=0
for u in $CLOSED_USERS; do
  id "$u" >/dev/null 2>&1 || continue
  sudo -n -u "$u" true 2>/dev/null || { as_owner rm -f "$PROBE"; die "cannot run commands as $u (sudo -n -u $u true failed), so the wall is unverified"; }
  if sudo -n -u "$u" ls "$VAULT_DIR" >/dev/null 2>&1; then
    say "WALL BROKEN: $u can list $VAULT_DIR"; fail=1
  else
    say "ok: $u cannot list $VAULT_DIR"
  fi
  if sudo -n -u "$u" cat "$PROBE" >/dev/null 2>&1; then
    say "WALL BROKEN: $u can read a file inside $VAULT_DIR"; fail=1
  else
    say "ok: $u cannot read a file inside it"
  fi
done
as_owner rm -f "$PROBE"
[ "$fail" = "0" ] || die "the wall does not hold; fix the permissions above before putting anything in the vault"

say "done. Next: cd $BRAIN_DIR && docker compose up -d api   then open Knowledge -> Vault (or GET /vault) and press Scan."
