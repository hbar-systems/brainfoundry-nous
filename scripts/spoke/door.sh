#!/bin/bash
# door.sh: the only thing the brain's key can run on the laptop. Created 2026-11-11 (SPOKE-1).
# Installed by spoke.sh as the forced command of one authorized_keys line:
#   from="<brain tailnet ip>",restrict,command="$HOME/.brain-spoke/door.sh" ssh-ed25519 ... brain-spoke:<handle>
# so the brain never gets a shell: it gets these verbs, each written to ~/.brain-spoke/door.log first.
#
#   facts                 what the computer is (model, chip, memory, macOS); never serial or UUID
#   inventory             counts and sizes by area, kind, age (inventory.sh); no names leave
#   log [n]               the last n lines of this log (default 50)
#   mode                  "look" (the start) or "organise"
#   organise on|off       the switch the friend's yes card turns on; off from the laptop too:
#                         bash ~/.brain-spoke/door.sh organise off
#   list <folder>         names in one folder (organise only)
#   peek <file>           the first 64 KB of one file (organise only)
#   apply                 a plan on stdin, lines "mkdir<TAB>folder" or "mv<TAB>from<TAB>to" (organise only);
#                         never overwrites, never deletes; writes an undo file and prints its id
#   undo <id>             moves a plan's files back
#   leave                 removes the brain's key line (the brain can let go of the laptop itself)
# Paths are relative to the home folder. Refused always: anything under Library, any hidden folder,
# .brain-spoke itself, "..", links that lead outside home. There is no delete verb and no shell.
set -u
LC_ALL=C; export LC_ALL
D="$HOME/.brain-spoke"
LOG="$D/door.log"
TAB="$(printf '\t')"
mkdir -p "$D/undo"

say() { printf '%s\n' "$*"; }
log() { printf '%s\t%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >> "$LOG"; }
refuse() { log "REFUSED	$*"; say "refused: $*" >&2; exit 3; }
mode() { cat "$D/mode" 2>/dev/null || echo look; }
need_organise() { [ "$(mode)" = organise ] || refuse "$1 needs organise mode (the friend's yes)"; }

safe() {
    # prints the absolute path for a home-relative path, or refuses
    local rel=$1 abs dir
    case "$rel" in ''|/*|*'..'*) refuse "path $rel" ;; esac
    case "/$rel/" in */.*/*|/Library/*) refuse "path $rel (hidden or Library)" ;; esac
    abs="$HOME/$rel"
    dir=$(cd -P "$(dirname "$abs")" 2>/dev/null && pwd -P) || refuse "path $rel (no such folder)"
    case "$dir/" in "$(cd -P "$HOME" && pwd -P)"/*) ;; *) refuse "path $rel (leads outside home)" ;; esac
    case "$dir/" in */Library/*|*/.*) refuse "path $rel (hidden or Library)" ;; esac
    printf '%s/%s\n' "$dir" "$(basename "$abs")"
}

# the brain's command arrives in SSH_ORIGINAL_COMMAND; run locally, the arguments
if [ -n "${SSH_ORIGINAL_COMMAND:-}" ]; then
    set -f; set -- $SSH_ORIGINAL_COMMAND; set +f
    WHO=brain
else
    WHO=laptop
fi
verb=${1:-}; shift 2>/dev/null || true
log "$WHO	$verb	$*"

case "$verb" in
    facts) bash "$D/inventory.sh" | awk -F'\t' '$1 == "meta" && $2 !~ /started|finished/' ;;
    inventory) bash "$D/inventory.sh" ;;
    log) tail -n "${1:-50}" "$LOG" ;;
    mode) mode ;;
    organise)
        case "${1:-}" in
            on) echo organise > "$D/mode"; say "organise on" ;;
            off) echo look > "$D/mode"; say "organise off" ;;
            *) refuse "organise needs on or off" ;;
        esac ;;
    list) need_organise list; p=$(safe "$*") || exit 3; [ -d "$p" ] || refuse "not a folder"; ls -1A "$p" | grep -v '^\.' ;;
    peek) need_organise peek; p=$(safe "$*") || exit 3; [ -f "$p" ] || refuse "not a file"; head -c 65536 "$p" ;;
    apply)
        need_organise apply
        id=$(date -u +%Y%m%dT%H%M%SZ); U="$D/undo/$id.tsv"; n=0
        while IFS="$TAB" read -r op a b; do
            case "$op" in
                mkdir) p=$(safe "$a") || exit 3; [ -e "$p" ] || { mkdir -p "$p" && printf 'rmdir\t%s\n' "$p" >> "$U"; n=$((n+1)); } ;;
                mv) s=$(safe "$a") || exit 3; t=$(safe "$b") || exit 3
                    [ -e "$s" ] || { say "skip (gone): $a"; continue; }
                    [ -e "$t" ] && { say "skip (would overwrite): $b"; continue; }
                    mv -n "$s" "$t" && printf 'mv\t%s\t%s\n' "$t" "$s" >> "$U" && n=$((n+1)) ;;
                '') ;;
                *) refuse "plan line $op" ;;
            esac
        done
        log "applied	$id	$n steps"; say "applied $n steps; undo id $id" ;;
    undo)
        U="$D/undo/${1:-none}.tsv"; [ -f "$U" ] || refuse "no undo $1"
        tail -r "$U" 2>/dev/null > "$U.rev" || tac "$U" > "$U.rev"
        while IFS="$TAB" read -r op a b; do
            case "$op" in
                mv) [ -e "$b" ] || mv -n "$a" "$b" ;;
                rmdir) rmdir "$a" 2>/dev/null ;;
            esac
        done < "$U.rev"
        mv "$U" "$U.undone"; rm -f "$U.rev"; say "undone $1" ;;
    leave)
        grep -v 'brain-spoke:' "$HOME/.ssh/authorized_keys" > "$HOME/.ssh/authorized_keys.spoke-tmp"
        mv "$HOME/.ssh/authorized_keys.spoke-tmp" "$HOME/.ssh/authorized_keys"; chmod 600 "$HOME/.ssh/authorized_keys"
        say "the brain's key is gone; run 'Leave my brain' on the Desktop to take the laptop off the network" ;;
    *) refuse "verb ${verb:-none}" ;;
esac
