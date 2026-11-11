#!/bin/bash
# inventory.sh: the spoke's first act, a read-only inventory of a laptop. Created 2026-11-11 (SPOKE-1).
# Runs ON the laptop (macOS bash 3.2 or Linux bash), reads file metadata only (size, date, extension),
# aggregates there and prints counts and sizes by area, kind and age as TSV on stdout.
# No file name, no folder name below the top level and no file content ever leaves the machine.
# Writes nothing: no temp file, no log, no cache. Errors (macOS privacy refusals) are counted, not shown.
#
#   bash inventory.sh            the inventory, TSV on stdout
#   bash inventory.sh --plan     print what it would read, read nothing
#   ssh <laptop> 'bash -s' < inventory.sh     run it with nothing installed (the dry-run door test)
#
# Never walked: ~/Library (apps' data: keychains, Messages, Mail, browsers), every hidden folder
# (.ssh, .gnupg, settings), other users' homes. Bundles (Photos library, Music library, apps,
# Logic and GarageBand projects) count as one item each, sized, never opened.
set -u
LC_ALL=C; export LC_ALL

STD_AREAS="Desktop Documents Downloads Pictures Music Movies Public Applications"
BUNDLES='*.photoslibrary *.musiclibrary *.tvlibrary *.imovielibrary *.fcpbundle *.app *.logicx *.band *.photosLibrary'

areas() {
    # "label<TAB>path" per area: the standard home folders by name, other visible home folders as one
    # area, external volumes by volume name.
    local d n
    for n in $STD_AREAS; do [ -d "$HOME/$n" ] && printf '%s\t%s\n' "$n" "$HOME/$n"; done
    for d in "$HOME"/*; do
        [ -d "$d" ] || continue
        n=${d##*/}
        case " $STD_AREAS Library " in *" $n "*) continue ;; esac
        printf 'other folders in home\t%s\n' "$d"
    done
    if [ -d /Volumes ]; then
        for d in /Volumes/*; do
            [ -d "$d" ] || continue
            [ -L "$d" ] && continue                      # "Macintosh HD" is a link to /
            n=${d##*/}
            case "$n" in com.apple.*|Recovery|Preboot|VM|Data) continue ;; esac
            printf 'drive: %s\t%s\n' "$n" "$d"
        done
    fi
}

if [ "${1:-}" = "--plan" ]; then
    echo "inventory plan (reads nothing now):"
    areas | while IFS="$(printf '\t')" read -r label path; do echo "  would read sizes and dates under: $label"; done
    echo "  never: ~/Library, hidden folders, other users; bundles counted whole, never opened"
    echo "  sends back: counts and sizes by area, kind and age; no names"
    exit 0
fi

if stat --version >/dev/null 2>&1; then STATFMT='-c'; FMT='F	%s	%Y	%n'; BFMT='B	0	%Y	%n'
else STATFMT='-f'; FMT='F	%z	%m	%N'; BFMT='B	0	%m	%N'; fi

prune_expr() {
    # find(1) pieces: bundles are printed with a B mark and pruned.
    local first=1 b IFS=' '
    for b in $BUNDLES; do
        if [ $first = 1 ]; then printf -- '-name\n%s\n' "$b"; first=0
        else printf -- '-o\n-name\n%s\n' "$b"; fi
    done
}

# facts: what the computer is (never serial number, UUID or user names)
if [ "$(uname -s)" = Darwin ]; then
    printf 'meta\tos\tmacOS %s\n' "$(sw_vers -productVersion 2>/dev/null)"
    system_profiler SPHardwareDataType 2>/dev/null | awk -F': ' '
        /Model Name/ {print "meta\tmodel\t" $2} /Model Identifier/ {print "meta\tmodel_id\t" $2}
        /Chip|Processor Name/ {print "meta\tchip\t" $2} /Memory:/ {print "meta\tmemory\t" $2}'
else
    printf 'meta\tos\t%s\n' "$(uname -sr)"
    printf 'meta\tmodel\t%s\n' "$(cat /sys/devices/virtual/dmi/id/product_name 2>/dev/null || echo unknown)"
fi
printf 'meta\tarch\t%s\n' "$(uname -m)"
df -k "$HOME" 2>/dev/null | awk 'NR==2 {print "meta\tdisk_kb\t" $2; print "meta\tfree_kb\t" $4}'
printf 'meta\tstarted\t%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
NOW=$(date +%s)

IFS_TAB="$(printf '\t')"
areas | while IFS="$IFS_TAB" read -r label path; do
    # one stream per area: F lines (files), B lines (bundles), "find:" lines (refusals)
    set -f; IFS='
'
    set -- $(prune_expr)
    IFS=' '; set +f
    { find "$path" -xdev \( -name '.*' ! -path "$path" \) -prune \
        -o -type d \( "$@" \) -prune -exec stat $STATFMT "$BFMT" {} + \
        -o -type f -exec stat $STATFMT "$FMT" {} + ; } 2>&1 | sed "s|^|$label$IFS_TAB|"
done | awk -F'\t' -v now="$NOW" '
function kind(n,   e) {
    e = tolower(n); sub(/.*\//, "", e)
    if (e !~ /\./) return "no extension"
    sub(/.*\./, "", e)
    if (e ~ /^(jpg|jpeg|heic|heif|png|gif|webp|tif|tiff|raw|cr2|cr3|nef|arw|dng|orf|rw2|bmp|psd)$/) return "photos and images"
    if (e ~ /^(mov|mp4|m4v|avi|mkv|webm|mts|3gp)$/) return "video"
    if (e ~ /^(wav|aif|aiff|mp3|m4a|flac|ogg|alac|aac|caf|opus)$/) return "audio"
    if (e ~ /^(als|alp|adg|adv|amxd|ptx|flp|rpp|logic|mid|midi|fxp|vstpreset|nmsv)$/) return "music projects and presets"
    if (e ~ /^(pdf|doc|docx|pages|txt|rtf|md|odt|key|ppt|pptx|numbers|xls|xlsx|csv|tsv|epub)$/) return "documents"
    if (e ~ /^(py|js|ts|tsx|jsx|sh|html|css|json|c|h|cpp|swift|go|rs|java|rb|ipynb|php|sql|yaml|yml|toml)$/) return "code"
    if (e ~ /^(zip|tar|gz|tgz|rar|7z|dmg|pkg|iso|xz|bz2)$/) return "archives and installers"
    return "other"
}
function age(t,   d) {
    d = (now - t) / 86400
    if (d < 30) return "last 30 days"; if (d < 365) return "this year"; if (d < 1095) return "1 to 3 years"; return "older than 3 years"
}
function bkind(n) {
    if (n ~ /\.(photoslibrary|photosLibrary)$/) return "photo library"
    if (n ~ /\.(musiclibrary|tvlibrary)$/) return "music or TV library"
    if (n ~ /\.(imovielibrary|fcpbundle)$/) return "video project library"
    if (n ~ /\.app$/) return "apps"
    return "Logic or GarageBand projects"
}
$2 == "F" {
    a = $1; s = $3 + 0; files++; bytes += s
    af[a]++; ab[a] += s
    k = kind($5); kf[a SUBSEP k]++; kb[a SUBSEP k] += s; K[k] = 1
    g = age($4); gf[a SUBSEP g]++; gb[a SUBSEP g] += s
    if (s >= 1073741824) { bigf++; bigb += s }
    n = tolower($5); sub(/.*\//, "", n)
    if (s >= 1048576) { key = s SUBSEP n; dc[key]++; if (dc[key] > 1) { dupf++; dupb += s } }
    next
}
$2 == "B" {
    a = $1; bp = $5; q = bp; gsub(/\x27/, "\x27\\\x27\x27", q)
    cmd = "du -sk \x27" q "\x27 2>/dev/null"; sz = 0
    if ((cmd | getline line) > 0) { split(line, w, " "); sz = w[1] * 1024 }
    close(cmd)
    k = bkind(bp); bf[a SUBSEP k]++; bb[a SUBSEP k] += sz; af[a]++; ab[a] += sz; bytes += sz
    next
}
$2 ~ /^find: / { blocked[$1]++; next }
END {
    for (a in ab) printf "area\t%s\t%d\t%.0f\n", a, af[a], ab[a]
    for (x in kf) { split(x, p, SUBSEP); printf "kind\t%s\t%s\t%d\t%.0f\n", p[1], p[2], kf[x], kb[x] }
    for (x in gf) { split(x, p, SUBSEP); printf "age\t%s\t%s\t%d\t%.0f\n", p[1], p[2], gf[x], gb[x] }
    for (x in bf) { split(x, p, SUBSEP); printf "bundle\t%s\t%s\t%d\t%.0f\n", p[1], p[2], bf[x], bb[x] }
    for (a in blocked) printf "blocked\t%s\t%d\n", a, blocked[a]
    printf "total\t%d\t%.0f\n", files, bytes
    printf "big\t%d\t%.0f\n", bigf, bigb
    printf "dups\t%d\t%.0f\n", dupf, dupb
}'
printf 'meta\tfinished\t%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
