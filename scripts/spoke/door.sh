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
#   undo <id>             moves a plan's files back (organise only)
#   leave                 removes the brain's key line (the brain can let go of the laptop itself)
#   move-in               (organise only) the token on stdin: starts brain_import.py --survey, the same
#                         helper as the home's pasted line, detached, its log in ~/.brain-spoke/move-in.log;
#                         it sends a LIST to the brain over https, waits for the yes on the home, brings
#                         exactly the chosen files and stops (SWITCH-1, 2026-11-16)
#   move-in status        whether it runs, and the last lines of its log
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

lower() { printf '%s' "$1" | tr '[:upper:]' '[:lower:]'; }

pyfind() {
    # a python3 that is really there. On a Mac /usr/bin/python3 is only Apple's stub until the Command
    # Line Tools are in (it would open Apple's install dialog instead of running), so it counts only then.
    local p
    for p in /opt/homebrew/bin/python3 /usr/local/bin/python3 /Library/Frameworks/Python.framework/Versions/Current/bin/python3; do
        [ -x "$p" ] && { echo "$p"; return 0; }
    done
    if [ "$(uname -s)" = Darwin ]; then
        xcode-select -p >/dev/null 2>&1 && [ -x /usr/bin/python3 ] && { echo /usr/bin/python3; return 0; }
        return 1
    fi
    command -v python3 2>/dev/null
}
running() { [ -f "$D/move-in.pid" ] && kill -0 "$(cat "$D/move-in.pid" 2>/dev/null)" 2>/dev/null; }

safe() {
    # prints the absolute path for a home-relative path, or refuses. The whole path is judged,
    # the last part included (audit 2026-11-13): a link as the last part is refused outright
    # (door.sh never needs to follow one), and the Library and hidden rules run on the resolved
    # path without regard to case, as macOS file names are case-insensitive.
    local rel=$1 abs dir base home lc
    case "$rel" in ''|/*|*'..'*) refuse "path $rel" ;; esac
    lc=$(lower "/$rel/")
    case "$lc" in */.*/*|/library/*) refuse "path $rel (hidden or Library)" ;; esac
    abs="$HOME/$rel"
    [ -L "$abs" ] && refuse "path $rel (a link)"
    dir=$(cd -P "$(dirname "$abs")" 2>/dev/null && pwd -P) || refuse "path $rel (no such folder)"
    home=$(cd -P "$HOME" && pwd -P)
    case "$dir/" in "$home"/*) ;; *) refuse "path $rel (leads outside home)" ;; esac
    base=$(basename "$abs")
    lc=$(lower "${dir#"$home"}/$base/")
    case "$lc" in */library/*|*/.*) refuse "path $rel (hidden or Library)" ;; esac
    printf '%s/%s\n' "$dir" "$base"
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
        # organise only, an id in apply's own format, every replayed path fenced again (audit 2026-11-13)
        need_organise undo
        case "${1:-}" in
            [0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]T[0-9][0-9][0-9][0-9][0-9][0-9]Z) ;;
            *) refuse "undo id ${1:-none}" ;;
        esac
        U="$D/undo/$1.tsv"; [ -f "$U" ] || refuse "no undo $1"
        H=$(cd -P "$HOME" && pwd -P)
        tail -r "$U" 2>/dev/null > "$U.rev" || tac "$U" > "$U.rev"
        while IFS="$TAB" read -r op a b; do
            case "$op" in
                mv) s=$(safe "${a#"$H"/}") || exit 3; t=$(safe "${b#"$H"/}") || exit 3
                    [ -e "$t" ] || mv -n "$s" "$t" ;;
                rmdir) p=$(safe "${a#"$H"/}") || exit 3; rmdir "$p" 2>/dev/null ;;
            esac
        done < "$U.rev"
        mv "$U" "$U.undone"; rm -f "$U.rev"; say "undone $1" ;;
    move-in)
        need_organise move-in
        case "${1:-}" in
            status) if running; then say "running"; else say "not running"; fi
                    tail -n "${2:-20}" "$D/move-in.log" 2>/dev/null | cut -c1-300; exit 0 ;;
            '') ;;
            *) refuse "move-in takes no words (the token comes on stdin)" ;;
        esac
        url=$(head -n 1 "$D/brain_url" 2>/dev/null)
        case "$url" in https://*) ;; *) refuse "no brain address in $D/brain_url (join again)" ;; esac
        case "$url" in *[!A-Za-z0-9.:/_-]*) refuse "brain address looks wrong" ;; esac
        [ -f "$D/brain_import.py" ] || refuse "no helper in $D (join again)"
        running && refuse "a move-in already runs"
        tok=""; IFS= read -r tok || true
        case "$tok" in imp_*) ;; *) refuse "move-in token" ;; esac
        case "${tok#imp_}" in *[!A-Za-z0-9_-]*|'') refuse "move-in token" ;; esac
        [ ${#tok} -le 70 ] || refuse "move-in token"
        py=$(pyfind) || refuse "python3 is not on this computer yet (on a Mac: Apple's Command Line Tools)"
        # detached: the run waits for the yes on the home for up to hours, and outlives this door call
        BRAIN_IMPORT_TOKEN="$tok" nohup "$py" "$D/brain_import.py" --survey --brain "$url" --receipt-dir "$D" \
            >> "$D/move-in.log" 2>&1 < /dev/null &
        echo $! > "$D/move-in.pid"
        log "move-in	started	pid $!"
        say "move-in started" ;;
    leave)
        grep -v 'brain-spoke:' "$HOME/.ssh/authorized_keys" > "$HOME/.ssh/authorized_keys.spoke-tmp"
        mv "$HOME/.ssh/authorized_keys.spoke-tmp" "$HOME/.ssh/authorized_keys"; chmod 600 "$HOME/.ssh/authorized_keys"
        say "the brain's key is gone; run 'Leave my brain' on the Desktop to take the laptop off the network" ;;
    *) refuse "verb ${verb:-none}" ;;
esac
