#!/bin/bash
# spoke.sh: make this Mac a spoke of its owner's brain, or take it off again. Created 2026-11-11 (SPOKE-1).
# Read it before you run it: every step below is printed before it happens, and --dry-run prints
# every step and changes nothing. Design: docs/spoke.md. Started by "Join my brain.command".
#
#   bash spoke.sh join [--dry-run]     join: Tailscale on the brain's own network, Remote Login, the door
#   bash spoke.sh leave [--dry-run]    remove the brain's key, take the laptop off the network, remove the door
#   bash spoke.sh status               what is installed, the mode, the last lines of the door log
#
# What it changes on join: installs the Tailscale app if missing (Apple-signed package from
# pkgs.tailscale.com, signature checked first; asks for your password once); logs Tailscale into
# your brain's own network with a one-time key that expires in an hour; asks you to turn on Remote
# Login for your user only; adds ONE line to ~/.ssh/authorized_keys that lets your brain run door.sh
# and nothing else; puts "Leave my brain.command" on your Desktop. Nothing else on the Mac changes.
set -u

# filled in by make-bundle.sh on your brain when you press "Download" on the console
HANDLE="@@HANDLE@@"                 # your brain's name
CONSOLE_URL="@@CONSOLE_URL@@"       # where you talk to it
LOGIN_SERVER="@@LOGIN_SERVER@@"     # your brain's network (its own coordination server)
AUTHKEY="@@AUTHKEY@@"               # one device, one use, expires an hour after download
BRAIN_IP="@@BRAIN_IP@@"             # your brain's address on that network; the key works only from it
BRAIN_KEY="@@BRAIN_KEY@@"           # your brain's public key (ssh-ed25519 ...)

D="$HOME/.brain-spoke"
TS="/Applications/Tailscale.app/Contents/MacOS/Tailscale"
PKG_URL="https://pkgs.tailscale.com/stable/Tailscale-latest-macos.pkg"
PKG_TEAM="(W5364U7YZB)"             # Tailscale Inc.'s Apple team id
HERE=$(cd "$(dirname "$0")" && pwd)
DRY=0; CMD=${1:-status}; [ "${2:-}" = "--dry-run" ] && DRY=1
n=0

step() { n=$((n+1)); printf '\n%d. %s\n' "$n" "$*"; }
run() {
    # every change goes through here: shown, then done (or only shown in a dry run)
    if [ $DRY = 1 ]; then printf '   would run: %s\n' "$*"; else printf '   running: %s\n' "$*"; "$@"; fi
}
note() { printf '   %s\n' "$*"; }
die() { printf '\nStopped: %s\nNothing after this step was changed.\n' "$*"; exit 1; }
is_mac() { [ "$(uname -s)" = Darwin ]; }

join() {
    [ $DRY = 1 ] && echo "DRY RUN: every step is printed, nothing is changed."
    step "Check this computer"
    if is_mac; then
        v=$(sw_vers -productVersion); note "macOS $v, $(uname -m)"
        [ "${v%%.*}" -ge 13 ] || die "macOS 13 or newer is needed (this is $v)"
    else
        [ $DRY = 1 ] && note "not a Mac: a real run would stop here" || die "this installer is for a Mac"
    fi
    [ "$(id -u)" = 0 ] && die "run it as yourself, not as root"
    case "$AUTHKEY$BRAIN_KEY" in *@@*) [ $DRY = 1 ] && note "(template copy: no key filled in yet)" || die "this copy was not made by your brain; download it from your console" ;; esac

    step "Tailscale, the private network between your brain and this laptop"
    if [ -x "$TS" ]; then note "already installed"
    else
        note "not installed: download the package from Tailscale and check Apple's signature before opening it"
        # A fresh private folder (mktemp -d, only this account can enter it), never a fixed
        # shared /tmp name another account could plant or swap during the password prompt
        # (audit 2026-11-13); a failed download stops here.
        if [ $DRY = 0 ]; then
            PKGDIR=$(mktemp -d "${TMPDIR:-/tmp}/brain-spoke.XXXXXXXX") || die "could not make a private download folder"
            chmod 700 "$PKGDIR"
        else PKGDIR="${TMPDIR:-/tmp}/brain-spoke.XXXXXXXX"; fi
        PKG="$PKGDIR/tailscale.pkg"
        run curl -fsSL -o "$PKG" "$PKG_URL" || die "the Tailscale download failed; not installed"
        if [ $DRY = 0 ]; then
            pkgutil --check-signature "$PKG" | grep -q "Developer ID Installer: Tailscale Inc. $PKG_TEAM" \
                || { rm -rf "$PKGDIR"; die "the package is not signed by Tailscale Inc.; not installed"; }
            note "signature: Developer ID Installer: Tailscale Inc. $PKG_TEAM"
        else note "would check: pkgutil --check-signature names Tailscale Inc. $PKG_TEAM, else stop"; fi
        note "macOS asks for your password now (the only time)"
        run sudo installer -pkg "$PKG" -target / || { rm -rf "$PKGDIR"; die "the Tailscale installer failed"; }
        run rm -rf "$PKGDIR"
    fi
    note "opening Tailscale: if macOS asks to add a VPN configuration, press Allow"
    run open -a Tailscale
    [ $DRY = 0 ] && sleep 5
    run "$TS" up --login-server="$LOGIN_SERVER" --auth-key="$AUTHKEY" --hostname="$HANDLE-laptop" --accept-dns=false --accept-routes=false

    step "Remote Login, the door your brain knocks on"
    if nc -z -G 2 127.0.0.1 22 >/dev/null 2>&1; then was=on; note "already on"
    else
        was=off
        note "System Settings opens at Sharing. Turn on Remote Login, then press the (i) beside it:"
        note "  Allow access for: Only these users, and keep only yourself ($(id -un))"
        note "  Allow full disk access for remote users: on (so your brain can see Documents, Desktop, Downloads)"
        run open "x-apple.systempreferences:com.apple.Sharing-Settings.extension"
        if [ $DRY = 0 ]; then
            for _ in $(seq 1 120); do nc -z -G 2 127.0.0.1 22 >/dev/null 2>&1 && break; sleep 5; done
            nc -z -G 2 127.0.0.1 22 >/dev/null 2>&1 || die "Remote Login did not come on within 10 minutes; run this again when ready"
            note "Remote Login is on"
        fi
    fi

    step "The door: one key line, one script, a log you can read"
    run mkdir -p "$D/undo" "$HOME/.ssh"
    run cp "$HERE/door.sh" "$HERE/inventory.sh" "$HERE/spoke.sh" "$D/"
    run chmod 700 "$D" "$HOME/.ssh"
    line="from=\"$BRAIN_IP\",restrict,command=\"$D/door.sh\" $BRAIN_KEY brain-spoke:$HANDLE"
    note "the line: $line"
    if [ $DRY = 0 ]; then
        grep -v 'brain-spoke:' "$HOME/.ssh/authorized_keys" 2>/dev/null > "$HOME/.ssh/authorized_keys.spoke-tmp"
        printf '%s\n' "$line" >> "$HOME/.ssh/authorized_keys.spoke-tmp"
        mv "$HOME/.ssh/authorized_keys.spoke-tmp" "$HOME/.ssh/authorized_keys"; chmod 600 "$HOME/.ssh/authorized_keys"
        echo look > "$D/mode"
        printf 'remote_login_before\t%s\njoined\t%s\n' "$was" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$D/state"
    else note "would add that line to ~/.ssh/authorized_keys (any older brain-spoke line replaced), mode look"; fi

    step "A way out on your Desktop"
    if [ $DRY = 0 ]; then
        printf '#!/bin/bash\nbash "$HOME/.brain-spoke/spoke.sh" leave\nread -r -p "Press Return to close." _\n' > "$HOME/Desktop/Leave my brain.command"
        chmod 755 "$HOME/Desktop/Leave my brain.command"
    else note "would write ~/Desktop/Leave my brain.command (runs: spoke.sh leave)"; fi

    step "Done"
    note "Go back to your brain: $CONSOLE_URL"
    note "It can now look (sizes and kinds, no names). It organises only after you say yes there."
}

leave() {
    [ $DRY = 1 ] && echo "DRY RUN: every step is printed, nothing is changed."
    step "Remove your brain's key"
    if [ $DRY = 0 ] && [ -f "$HOME/.ssh/authorized_keys" ]; then
        grep -v 'brain-spoke:' "$HOME/.ssh/authorized_keys" > "$HOME/.ssh/authorized_keys.spoke-tmp"
        mv "$HOME/.ssh/authorized_keys.spoke-tmp" "$HOME/.ssh/authorized_keys"; chmod 600 "$HOME/.ssh/authorized_keys"
        note "removed"
    else note "would remove every line marked brain-spoke: from ~/.ssh/authorized_keys"; fi
    step "Take this laptop off your brain's network"
    [ -x "$TS" ] && run "$TS" logout || note "Tailscale is not installed"
    note "the Tailscale app stays; to remove it, drag it from Applications to the Bin"
    step "Remote Login"
    if grep -q 'remote_login_before	off' "$D/state" 2>/dev/null; then
        note "it was off before you joined: System Settings opens at Sharing, turn Remote Login off"
        run open "x-apple.systempreferences:com.apple.Sharing-Settings.extension"
    else note "it was on before you joined (or unknown): left as it is"; fi
    step "Remove the door"
    note "your door log is kept at ~/brain-spoke-door.log"
    run cp "$D/door.log" "$HOME/brain-spoke-door.log"
    run rm -rf "$D"
    run rm -f "$HOME/Desktop/Leave my brain.command"
    step "Done: your brain can no longer reach this laptop."
}

status() {
    [ -d "$D" ] || { echo "not joined"; exit 0; }
    printf 'mode: %s\n' "$(cat "$D/mode" 2>/dev/null)"
    cat "$D/state" 2>/dev/null
    grep -c 'brain-spoke:' "$HOME/.ssh/authorized_keys" 2>/dev/null | sed 's/^/key lines: /'
    [ -x "$TS" ] && "$TS" status 2>/dev/null | head -3
    echo "last door lines:"; tail -n 10 "$D/door.log" 2>/dev/null
}

case "$CMD" in
    join) join ;;
    leave) leave ;;
    status) status ;;
    *) sed -n '6,9p' "$0"; exit 2 ;;
esac
