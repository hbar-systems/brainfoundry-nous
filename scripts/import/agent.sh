#!/bin/bash
# Bring in this computer (SPOKE-3 "Courier", hbar 2026-11-16). The one line from your brain's home:
#
#   curl -fsSL https://<your brain>/api/bf/laptop/agent.sh | bash -s -- imp_...
#
# What it does, once, then it is gone:
#  1. It looks through your home folder and your cloud folders (iCloud Drive, Google Drive, Dropbox,
#     OneDrive, Box), and the session history of Codex and Claude Code (~/.codex/sessions,
#     ~/.claude/projects: only the session files, nothing else in those folders): names, sizes and
#     dates only. Nothing is read yet.
#  2. It sends that LIST to your own brain over HTTPS, with the one-time key in the line.
#     Never listed, only counted: hidden files, keys, passwords, mail, browser data, system folders.
#  3. You choose on your brain's home what to bring. It then sends exactly those files, and only
#     files it listed itself, then closes the key.
#  4. It deletes its temporary folder and stops. Nothing is installed, nothing keeps running, and
#     your brain has no way into this computer: this program only ever calls out to your brain.
#
# It runs as you, needs no password and no admin, and uses what every Mac has: bash, curl, find,
# stat, awk, gzip. The never-send rules below come from scripts/import/brain_import.py on the
# brain (one source). Read it before you run it: open the address above in a browser.
# Docs: docs/IMPORT.md, "Bring in this computer" (brainfoundry-nous).

main() {
set -u
umask 077
AGENT_VERSION="agent-sh/0.1.0"
TOKEN="${1:-}"
BASE="${2:-@@BASE@@}"
POLL="${BRAIN_AGENT_POLL:-3}"
HOME_DIR="${BRAIN_AGENT_HOME:-$HOME}"

# ── words (@@LANG@@) ──
@@WORDS@@

say() { printf '%s\n' "$*"; }
sayf() { local f="$1"; shift; printf "$f\n" "$@"; }

# ── never-send rules (from brain_import.py on the brain) ──
SKIP_DIRS=(@@SKIP_DIRS@@)
SKIP_DIR_SUFFIXES=(@@DIR_SUFFIXES@@)
export BA_SECRET_RE='@@SECRET_RE@@'
export BA_READABLE=' @@READABLE@@ '
export BA_AUDIO=' @@AUDIO@@ '
export BA_MAX_FILE=@@MAX_FILE@@
export BA_MAX_AUDIO=@@MAX_AUDIO@@
export BA_MAX_ENTRIES=@@MAX_ENTRIES@@
export BA_MAX_NAME=400
IMAGES=' @@IMAGES@@ '
# the coding agents' history: label|folder under the home|deepest file (path parts, 0 any)
HISTORY_ROOTS=(@@HISTORY@@)

LOOK=0
[ "$TOKEN" = "--look" ] && LOOK=1  # look only: walk and count here, send nothing, no key needed
case "$TOKEN" in
  imp_*|--look) ;;
  *) say "$W_BADTOKEN"; exit 2 ;;
esac
if [ "$LOOK" = 0 ] && ! printf '%s' "$TOKEN" | grep -Eq '^imp_[A-Za-z0-9_-]{32,64}$'; then say "$W_BADTOKEN"; exit 2; fi
case "$BASE" in
  https://*) ;;
  http://127.0.0.1:*|http://localhost:*|http://127.0.0.1|http://localhost) ;;
  *) say "$W_BADBASE"; exit 2 ;;
esac
BASE="${BASE%/}"
for tool in curl find stat awk gzip mktemp; do
  command -v "$tool" >/dev/null 2>&1 || { sayf "$W_MISSING" "$tool"; exit 3; }
done

TMP="$(mktemp -d "${TMPDIR:-/tmp}/brain-agent.XXXXXX")" || exit 3
FINISHED=0
cleanup() { rm -rf "$TMP"; }
trap cleanup EXIT
# the key goes to curl from a file, never on its command line (other programs can read those)
printf 'Authorization: Bearer %s\n' "$TOKEN" > "$TMP/auth"

api() {  # api <method> <path> [curl args...] -> prints the HTTP code; body in $TMP/out
  local method="$1" path="$2"; shift 2
  curl -sS -X "$method" -o "$TMP/out" -w '%{http_code}' -H @"$TMP/auth" -A "$AGENT_VERSION" \
    --connect-timeout 20 "$@" "$BASE$path" 2>"$TMP/curlerr" || printf '000'
}
detail() { sed -n 's/.*"detail" *: *"\([^"]*\)".*/\1/p' "$TMP/out" | head -1; }
finish() {
  [ "$FINISHED" = 1 ] && return
  FINISHED=1
  api POST /documents/import-laptop/finish >/dev/null
}
on_stop() { finish; printf '\n'; say "$W_ABORTED"; exit 130; }
trap on_stop INT TERM
human() { awk -v n="$1" 'BEGIN { split("B KB MB GB TB", u, " "); i = 1; while (n >= 1024 && i < 5) { n /= 1024; i++ }
  if (i == 1) printf "%d %s", n, u[i]; else printf "%.1f %s", n, u[i] }'; }

# ── 1. the key ──
if [ "$LOOK" = 1 ]; then FINISHED=1; code=200; printf '{"survey":true}' > "$TMP/out"; else
code="$(api GET /documents/import-laptop/check)"; fi
if [ "$code" != 200 ]; then
  if [ "$code" = 000 ]; then sayf "$W_REFUSED" "no answer" "$(head -c 200 "$TMP/curlerr")"
  else sayf "$W_REFUSED" "$code" "$(detail)"; fi
  exit 4
fi
if ! grep -q '"survey" *: *true' "$TMP/out"; then say "$W_NOTSURVEY"; exit 4; fi
[ "$LOOK" = 0 ] && say "$W_CONNECTED"

# ── 2. where to look: the home folder, then the cloud folders it has (label<TAB>folder) ──
: > "$TMP/roots"
addroot() { [ -d "$2" ] && [ ! -L "$2" ] && printf '%s\t%s\n' "$1" "$2" >> "$TMP/roots"; }
addroot "iCloud Drive" "$HOME_DIR/Library/Mobile Documents/com~apple~CloudDocs"
if [ -d "$HOME_DIR/Library/CloudStorage" ]; then
  for p in "$HOME_DIR/Library/CloudStorage"/*; do
    [ -d "$p" ] || continue
    low="$(basename "$p" | tr '[:upper:]' '[:lower:]')"
    case "$low" in
      googledrive*) if [ -d "$p/My Drive" ]; then addroot "Google Drive" "$p/My Drive"; else addroot "Google Drive" "$p"; fi ;;
      dropbox*) addroot "Dropbox" "$p" ;;
      onedrive*) addroot "OneDrive" "$p" ;;
      box*) addroot "Box" "$p" ;;
    esac
  done
fi
for p in "$HOME_DIR"/*; do
  [ -d "$p" ] && [ ! -L "$p" ] || continue
  low="$(basename "$p" | tr '[:upper:]' '[:lower:]')"
  case "$low" in
    "icloud drive"|iclouddrive) addroot "iCloud Drive" "$p" ;;
    "google drive"|"my drive") addroot "Google Drive" "$p" ;;
    dropbox|"dropbox ("*) addroot "Dropbox" "$p" ;;
    onedrive|"onedrive - "*) addroot "OneDrive" "$p" ;;
    box) addroot "Box" "$p" ;;
  esac
done
# a second account of the same cloud gets "(2)"
awk -F '\t' '{ n[$1]++; print (n[$1] == 1 ? $1 : $1 " (" n[$1] ")") "\t" $2 }' "$TMP/roots" > "$TMP/roots2"
# the coding agents' history (label<TAB>folder<TAB>depth): only these two folders under ~/.codex and
# ~/.claude, never the rest (auth.json, config, credentials); no link followed
: > "$TMP/hist"
for h in "${HISTORY_ROOTS[@]}"; do
  label="${h%%|*}"; rest="${h#*|}"; sub="${rest%%|*}"; depth="${rest##*|}"
  top="$HOME_DIR/${sub%%/*}"
  [ -d "$top" ] && [ ! -L "$top" ] && [ -d "$HOME_DIR/$sub" ] && [ ! -L "$HOME_DIR/$sub" ] &&
    printf '%s\t%s\t%s\n' "$label" "$HOME_DIR/$sub" "$depth" >> "$TMP/hist"
done

# ── 3. the walk: find prunes the never-entered folders, stat gives size and date, awk keeps the rules ──
if stat --version >/dev/null 2>&1; then STAT=(stat --printf '%s\t%Y\t%n\n'); else STAT=(stat -f '%z%t%m%t%N'); fi
PRUNE=(-name '.*')
for d in "${SKIP_DIRS[@]}"; do PRUNE+=(-o -iname "$d"); done
for s in "${SKIP_DIR_SUFFIXES[@]}"; do PRUNE+=(-o -iname "*$s"); done
NL='
'
TAB='	'
say "$W_LOOKING"
[ "$(uname -s)" = Darwin ] && say "$W_MACASK"
: > "$TMP/rows"; : > "$TMP/places"; : > "$TMP/skipped"; : > "$TMP/private"
walk() {  # walk <label> <root> [history depth]
  local label="$1" root="$2" hist="${3:-}" cloudprune=()
  if [ -z "$label" ]; then  # the cloud folders inside the home are walked as their own roots
    while IFS="$TAB" read -r _l cp; do cloudprune+=(-o -path "$cp"); done < "$TMP/roots2"
  fi
  find "$root" -mindepth 1 \( -type d \( "${PRUNE[@]}" ${cloudprune[@]+"${cloudprune[@]}"} \) -prune \) -o \
    \( -type f ! -path "*$NL*" ! -path "*$TAB*" ! -path '*\\*' -exec "${STAT[@]}" {} + \) 2>>"$TMP/finderr" |
  BA_ROOT="$root" BA_LABEL="$label" BA_HIST="$hist" awk -F '\t' -v have="$(awk 'END { print NR }' "$TMP/places")" -v rows="$TMP/rows" -v places="$TMP/places" -v skipped="$TMP/skipped" '
    function jq(s) { gsub(/"/, "\\\"", s); return "\"" s "\"" }
    BEGIN { root = ENVIRON["BA_ROOT"]; label = ENVIRON["BA_LABEL"]; sre = ENVIRON["BA_SECRET_RE"]
      readable = ENVIRON["BA_READABLE"]; audio = ENVIRON["BA_AUDIO"]; maxf = ENVIRON["BA_MAX_FILE"] + 0
      maxa = ENVIRON["BA_MAX_AUDIO"] + 0; maxn = ENVIRON["BA_MAX_ENTRIES"] + 0; maxname = ENVIRON["BA_MAX_NAME"] + 0
      hist = ENVIRON["BA_HIST"]; have += 0 }
    {
      size = $1 + 0; mtime = $2 + 0; path = $0; sub(/^[^\t]*\t[^\t]*\t/, "", path)
      if (substr(path, 1, length(root) + 1) != root "/") next
      rel = substr(path, length(root) + 2)
      base = rel; sub(/.*\//, "", base); low = tolower(base)
      top = (index(rel, "/") ? substr(rel, 1, index(rel, "/") - 1) : "(home)")
      key = (label != "" ? label "/" top : top)
      name = (label != "" ? label "/" rel : rel)
      ext = (index(base, ".") ? tolower(base) : ""); sub(/.*\./, "", ext)
      why = ""
      if (substr(base, 1, 1) == ".") why = "hidden"
      else if (low ~ sre) why = "secret"
      else if (hist != "") {  # a history root: session files only
        if (ext != "@@HISTORY_EXT@@" || (hist + 0 > 0 && split(rel, _parts, "/") > hist + 0)) why = "not a chat"
        else if (size > maxf) why = "over 25 MB"
        else if (size == 0) why = "empty"
        else if (length(name) > maxname) why = "name too long or odd"
      }
      else if (ext == "" || (index(readable, " " ext " ") == 0 && index(audio, " " ext " ") == 0)) why = "not readable by Knowledge"
      else if (index(audio, " " ext " ") && size > maxa) why = "over 200 MB"
      else if (!index(audio, " " ext " ") && size > maxf) why = "over 25 MB"
      else if (size == 0) why = "empty"
      else if (length(name) > maxname || name ~ /^[A-Za-z]:/) why = "name too long or odd"
      if (why != "") { skip[key ": " why]++; next }
      if (have >= maxn) { skip[key ": over the list limit"]++; next }
      have++
      printf "%s[%s,%d,%d]", (have > 1 ? "," : ""), jq(name), size, mtime >> rows
      printf "%s\t%s\t%d\n", name, path, size >> places
    }
    END { for (k in skip) printf "%s\t%d\n", k, skip[k] >> skipped }'
}
walk "" "$HOME_DIR"
while IFS="$TAB" read -r label root; do
  sayf "$W_ROOT" "$label"
  walk "$label" "$root"
done < "$TMP/roots2"
while IFS="$TAB" read -r label root depth; do
  sayf "$W_ROOT" "$label"
  walk "$label" "$root" "$depth"
done < "$TMP/hist"

# folders the system kept private (macOS privacy, or no permission): named, not looked into
sed -n -e 's/^find: \(.*\): Operation not permitted$/\1/p' -e 's/^find: \(.*\): Permission denied$/\1/p' "$TMP/finderr" |
  sed -e "s/^'\\(.*\\)'\$/\\1/" -e 's/^‘\(.*\)’$/\1/' |
  while IFS= read -r p; do
    rel="${p#"$HOME_DIR"/}"
    [ "$rel" = "$p" ] && rel="$(basename "$p")"
    printf '%s\n' "${rel%%/*}"
  done | sort -u > "$TMP/private"

n_rows="$(awk -F '\t' 'END { print NR }' "$TMP/places")"
total="$(awk -F '\t' '{ s += $3 } END { printf "%d", s }' "$TMP/places")"
sayf "$W_FOUND" "$n_rows" "$(human "${total:-0}")"
clouds="$(cut -f1 "$TMP/roots2" | awk 'NR > 1 { printf ", " } { printf "%s", $0 }')"
if [ -n "$clouds" ]; then sayf "$W_CLOUDS" "$clouds"; else say "$W_NOCLOUDS"; fi
hists="$(cut -f1 "$TMP/hist" | awk 'NR > 1 { printf ", " } { printf "%s", $0 }')"
[ -n "$hists" ] && sayf "$W_HISTORY" "$hists"
n_skip="$(awk -F '\t' '{ s += $2 } END { printf "%d", s }' "$TMP/skipped")"
[ "$n_skip" -gt 0 ] && sayf "$W_NEVER" "$n_skip"
if [ -s "$TMP/private" ]; then
  sayf "$W_PRIVATE" "$(awk 'NR > 1 { printf ", " } { printf "%s", $0 }' "$TMP/private")"
fi

if [ "$LOOK" = 1 ]; then
  awk -F '\t' '{ k = $1; sub(/\/.*/, "", k); n[k]++ } END { for (k in n) printf "  %s: %d\n", k, n[k] }' "$TMP/places" | sort
  say "$W_LOOKONLY"
  exit 0
fi

# ── 4. the list goes to the brain (gzip JSON; names, sizes, dates; no content) ──
jesc() { awk '{ gsub(/"/, "\\\""); printf "\"%s\"", $0 }'; }
{
  printf '{"version":"%s","os":"%s","files":[' "$AGENT_VERSION" "$(uname -s | tr '[:upper:]' '[:lower:]')"
  cat "$TMP/rows"
  printf '],"skipped":{'
  {
    awk -F '\t' '{ k = $1; gsub(/"/, "\\\"", k); printf "%s\"%s\":%d", (NR > 1 ? "," : ""), k, $2 }' "$TMP/skipped"
    [ -s "$TMP/skipped" ] && [ -s "$TMP/private" ] && printf ','
    awk '{ k = $0 ": kept private by the system"; gsub(/"/, "\\\"", k); printf "%s\"%s\":0", (NR > 1 ? "," : ""), k }' "$TMP/private"
  }
  printf '},"roots":['
  { cut -f1 "$TMP/roots2"; cut -f1 "$TMP/hist"; } | awk '{ k = $0; gsub(/"/, "\\\"", k); printf "%s\"%s\"", (NR > 1 ? "," : ""), k }'
  printf ']}'
} | gzip -c > "$TMP/inv.gz"
code="$(api POST /documents/import-laptop/check -H 'Content-Type: application/json' -H 'Content-Encoding: gzip' --data-binary @"$TMP/inv.gz")"
if [ "$code" != 200 ]; then sayf "$W_REFUSED" "$code" "$(detail)"; finish; exit 5; fi
g_files="$(sed -n 's/.*"files" *: *\([0-9]*\).*/\1/p' "$TMP/out")"
g_groups="$(sed -n 's/.*"groups" *: *\([0-9]*\).*/\1/p' "$TMP/out")"
printf '\n'
sayf "$W_LISTSENT" "${g_files:-0}" "${g_groups:-0}"
say "$W_CHOOSE"

# ── 5. wait for the choice on the home ──
while :; do
  sleep "$POLL"
  code="$(api GET '/documents/import-laptop/check?form=lines')"
  if [ "$code" = 401 ]; then say "$W_EXPIRED"; FINISHED=1; exit 0; fi
  [ "$code" = 200 ] || continue
  if head -1 "$TMP/out" | grep -q '^state chosen$'; then break; fi
done
tail -n +2 "$TMP/out" > "$TMP/take"

# ── 6. bring exactly what was chosen, and only names this run listed itself ──
awk -F '\t' 'NR == FNR { p[$1] = $2; z[$1] = $3; next } ($2 in p) { print $1 "\t" $2 "\t" p[$2] "\t" z[$2]; next } { miss++ }
  END { printf "%d\n", miss > "/dev/stderr" }' "$TMP/places" "$TMP/take" > "$TMP/send" 2>"$TMP/miss"
n_send="$(awk 'END { print NR }' "$TMP/send")"
n_miss="$(cat "$TMP/miss")"
send_total="$(awk -F '\t' '{ s += $4 } END { printf "%d", s }' "$TMP/send")"
printf '\n'
sayf "$W_CHOSE" "$n_send" "$(human "${send_total:-0}")"
[ "${n_miss:-0}" -gt 0 ] && sayf "$W_IGNORED" "$n_miss"
i=0; sent=0; refused=0
while IFS="$TAB" read -r kind name path _size; do
  i=$((i + 1))
  ext="${name##*.}"; ext="$(printf '%s' "$ext" | tr '[:upper:]' '[:lower:]')"
  keep=""
  [ "$kind" = files ] && case "$IMAGES" in *" $ext "*) keep=file ;; esac
  q="${path//\"/\\\"}"
  if [ -f "$path" ] && [ ! -L "$path" ]; then
    code="$(api POST /documents/import-laptop/file --form-string "path=$name" --form-string "keep=$keep" -F "file=@\"$q\"")"
  else
    code=404; printf '{"detail":"not on this computer any more"}' > "$TMP/out"
  fi
  if [ "$code" = 200 ]; then
    sent=$((sent + 1))
    if grep -q '"where"' "$TMP/out"; then mark="$W_KEPT"; else mark="$W_OK"; fi
  else
    refused=$((refused + 1)); mark="$(printf "$W_REFUSEDONE" "$code $(detail)")"
  fi
  printf '[%d/%d] %s  %s\n' "$i" "$n_send" "$name" "$mark"
  if [ "$code" = 401 ]; then say "$W_STOPPED"; break; fi
done < "$TMP/send"

finish
printf '\n'
sayf "$W_DONE" "$sent" "$refused"
}

main "$@"
