#!/bin/bash
# make-bundle.sh: on the brain, build the signed "Join my brain" zip for one laptop. Created 2026-11-11 (SPOKE-1).
# The console's Download button runs this after the brain has issued a one-time network key for the
# device; the zip is served once, over https, behind the console login. Never run on the laptop.
#
#   bash make-bundle.sh --handle H --console URL --login-server URL --authkey-file F \
#        --brain-ip IP --brain-pubkey F --signing-key F --out DIR [--lang en|ru]
#
# The zip holds one thing, "Join my brain.app" (SWITCH-1, 2026-11-16): Safari unpacks it into Downloads and
# the owner double-clicks it; no Terminal. Inside, Contents/Resources holds every file as text (spoke.sh,
# door.sh, inventory.sh, brain_import.py, words.sh, the .command for a Terminal start, WHAT-THIS-DOES.txt)
# with SHA256SUMS and its signature. Unsigned by Apple: macOS asks once (docs/spoke.md, section 12).
#
# The signing key is the brain's own (ssh-keygen -t ed25519, namespace brain-spoke); its fingerprint is
# shown on the console page next to the Download button, and the .command prints the same fingerprint.
# The zip holds the one-time network key: it expires an hour after issue and works for one device.
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
while [ $# -gt 0 ]; do
    case "$1" in
        --handle) H=$2 ;; --console) C=$2 ;; --login-server) L=$2 ;; --authkey-file) A=$2 ;;
        --brain-ip) IP=$2 ;; --brain-pubkey) PK=$2 ;; --signing-key) SK=$2 ;; --out) OUT=$2 ;; --lang) LG=$2 ;;
        *) sed -n '5,7p' "$0" >&2; exit 2 ;;
    esac; shift 2
done
for v in H C L A IP PK SK OUT; do [ -n "${!v:-}" ] || { echo "make-bundle: missing --${v}" >&2; exit 2; }; done
case "$H" in *[!a-z0-9-]*|'') echo "make-bundle: handle must be a-z 0-9 -" >&2; exit 2 ;; esac
case "$IP" in *[!0-9.:a-f]*) echo "make-bundle: brain ip looks wrong" >&2; exit 2 ;; esac
LG=${LG:-en}; case "$LG" in en|ru) ;; *) echo "make-bundle: lang is en or ru" >&2; exit 2 ;; esac
# the move-in helper: beside this script once installed (/usr/local/share/spoke), else the repo's own
HELPER="$HERE/brain_import.py"; [ -f "$HELPER" ] || HELPER="$HERE/../import/brain_import.py"
[ -f "$HELPER" ] || { echo "make-bundle: brain_import.py not found" >&2; exit 2; }
APPSRC="$HERE/app"; [ -d "$APPSRC" ] || APPSRC="$HERE"

W=$(mktemp -d); trap 'rm -rf "$W"' EXIT
APP="$W/Join my brain.app"; B="$APP/Contents/Resources"; mkdir -p "$B" "$APP/Contents/MacOS"
cp "$APPSRC/Info.plist" "$APP/Contents/Info.plist"
cp "$APPSRC/join-my-brain" "$APP/Contents/MacOS/join-my-brain"
cp "$HERE/door.sh" "$HERE/inventory.sh" "$HERE/words.sh" "$HERE/Join my brain.command" "$HERE/WHAT-THIS-DOES.txt" "$B/"
cp "$HELPER" "$B/brain_import.py"
printf '%s\n' "$LG" > "$B/lang"
python3 - "$HERE/spoke.sh" "$B/spoke.sh" "$H" "$C" "$L" "$A" "$IP" "$PK" "$LG" <<'PY'
import sys
src, dst, h, c, l, a, ip, pk, lg = sys.argv[1:]
s = open(src).read()
key = open(a).read().strip(); pub = open(pk).read().split()
for name, val in (("HANDLE", h), ("CONSOLE_URL", c), ("LOGIN_SERVER", l), ("AUTHKEY", key),
                  ("BRAIN_IP", ip), ("BRAIN_KEY", " ".join(pub[:2])), ("LANG", lg)):
    if '"' in val or "$" in val or "`" in val or "\n" in val:
        sys.exit(f"make-bundle: {name} has a character that is not allowed")
    s = s.replace(f"@@{name}@@", val)
assert "@@" not in s.split("set -u", 1)[1].split('D="$HOME', 1)[0], "placeholder left"
open(dst, "w").write(s)
PY
chmod 755 "$B/spoke.sh" "$B/door.sh" "$B/inventory.sh" "$B/Join my brain.command" "$APP/Contents/MacOS/join-my-brain"
ssh-keygen -y -f "$SK" > "$B/allowed_signers.pub"
printf 'brain namespaces="brain-spoke" %s\n' "$(cat "$B/allowed_signers.pub")" > "$B/allowed_signers"
(cd "$B" && sha256sum spoke.sh door.sh inventory.sh words.sh brain_import.py lang "Join my brain.command" WHAT-THIS-DOES.txt \
    allowed_signers ../Info.plist ../MacOS/join-my-brain > SHA256SUMS)
ssh-keygen -Y sign -q -f "$SK" -n brain-spoke "$B/SHA256SUMS"
mkdir -p "$OUT"
python3 - "$W" "$OUT/join-my-brain-$H.zip" <<'PY'
import os, sys, zipfile
root, dst = sys.argv[1:]
with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as z:
    for d, _, files in os.walk(root):
        for f in sorted(files):
            p = os.path.join(d, f); rel = os.path.relpath(p, root)
            i = zipfile.ZipInfo.from_file(p, rel); i.compress_type = zipfile.ZIP_DEFLATED
            i.external_attr = (os.stat(p).st_mode & 0o777 | 0o100000) << 16   # keep the execute bit for Finder
            z.writestr(i, open(p, "rb").read())
PY
chmod 600 "$OUT/join-my-brain-$H.zip"
echo "$OUT/join-my-brain-$H.zip"
ssh-keygen -lf "$B/allowed_signers.pub" | awk '{print "signing key: " $2}'
