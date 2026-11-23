#!/usr/bin/env bash
# member-ready.sh: is this member brain ready? (MEMBERS-11, 2026-11-23)
# Ready = the member opens it and their daily work is the first thing they can press, easier than before
# (docs/MEMBER_READY.md). One GREEN/RED line per item of the standard. READ ONLY: it changes nothing,
# prints no secret value (key lines are counted, never shown), and never sends a chat.
#
#   on a shared box:   bash member-ready.sh <handle> <lang> [<start-page-sha12>]
#   on its own box:    bash member-ready.sh --single <lang> [<start-page-sha12>]
# Needs sudo (reads the member's layout, .env counts and Caddyfile lines), docker compose, curl, python3.
set -u
if [ "${1:-}" = --single ]; then
  m=$(hostname); D=/home/hbar/brain; P=8010; UI=3010
  B=$(systemctl cat cc-bridge 2>/dev/null | sed -n 's/^Environment=CC_PORT=\([0-9]*\).*/\1/p' | tail -1); B=${B:-7682}
  CCU=$(systemctl cat cc-bridge 2>/dev/null | sed -n 's/^User=//p' | tail -1); CCU=${CCU:-cc}
  HOSTNAMES="console."
else
  m=$1; n=$(sudo awk -v h="$m" '$1==h{print $2}' /srv/brains/members.tsv)
  [ -n "$n" ] || { echo "RED  0 member: $m is not in /srv/brains/members.tsv"; exit 0; }
  D=/srv/brains/$m; P=$((8100+10*n)); UI=$((P+1)); B=$((P+8)); CCU=$m-cc
  HOSTNAMES="console.$m."
fi
LANG_WANT=${2:-en}; SHA_WANT=${3:-}
g=0; r=0
say() { if [ "$1" = G ]; then g=$((g+1)); echo "GREEN $2"; else r=$((r+1)); echo "RED   $2"; fi; }
CCH=$(getent passwd "$CCU" | cut -d: -f6)

# 1 up: the console and its bridge answer
u=$(curl -s -o /dev/null -w '%{http_code}' -m 20 "localhost:$UI/"); h=$(curl -s -o /dev/null -w '%{http_code}' -m 20 "localhost:$P/health")
HEALTH=$(curl -s -m 25 "localhost:$B/cc/health")
[ "$u" = 200 ] && [ "$h" = 200 ] && [ -n "$HEALTH" ] && say G "1 up: console $u, api $h, bridge answers" || say R "1 up: console $u, api $h, bridge ${HEALTH:+answers}${HEALTH:-down}"

# 2 current: the member runs the template's main (fixes reach them)
head=$(git -C "$D" rev-parse --short HEAD 2>/dev/null); orig=$(git -C "$D" ls-remote origin refs/heads/main 2>/dev/null | cut -c1-7)
[ -n "$head" ] && [ "$head" = "$orig" ] && say G "2 current: $head = origin main" || say R "2 current: $head, origin main $orig"

# 3 persona: their own words, readable by BOTH the api and the console reasoner (2026-11-22: a host copy was missing)
pr=$(cd "$D" && sudo docker compose exec -T api sh -c 'wc -c < /app/runtime/brain_persona.local.md' </dev/null 2>/dev/null | tr -dc 0-9)
ph=$(sudo sh -c "wc -c < '$D/api/brain_persona.local.md'" 2>/dev/null | tr -dc 0-9)
[ "${pr:-0}" -gt 200 ] && [ "${ph:-0}" -gt 200 ] && say G "3 persona: api ${pr} chars, console copy ${ph} chars" || say R "3 persona: api ${pr:-none}, console copy ${ph:-none} (both needed, over 200 chars)"

# 4 language: the console speaks theirs
LAY=$(sudo python3 -c '
import json,sys
try: d=json.load(open(sys.argv[1]))
except Exception: print("none - none none"); sys.exit()
c=d.get("current") or {}; p=c.get("panels") or {}
q=p.get("hero") is False and p.get("nav") is False and p.get("tools") is False
print(d.get("lang") or "en", c.get("start") or "-", "quiet" if q else "stock")' "$CCH/.cc-bridge/layout.json" 2>/dev/null)
read -r lang start quiet <<<"${LAY:-none - none}"
[ "$lang" = "$LANG_WANT" ] && say G "4 language: $lang" || say R "4 language: $lang, wanted $LANG_WANT"

# 5 first screen: opens on their start page (Week app), not the stock menu
OUT=$(printf '%s' "$HEALTH" | python3 -c 'import sys,json
try: print(json.load(sys.stdin).get("out") or "")
except Exception: print("")' 2>/dev/null)
PAGE="$OUT/week/index.html"; have=""
[ -n "$OUT" ] && sudo test -s "$PAGE" && have=$(sudo sha256sum "$PAGE" | cut -c1-12)
week=$(cd "$D" && sudo docker compose exec -T api python - </dev/null 2>/dev/null <<'PY'
import os, requests
H={"X-Api-Key": os.environ.get("BRAIN_API_KEY","")}
a={x.get("id"): x for x in (requests.get("http://localhost:8000/apps/list", headers=H, timeout=30).json().get("apps") or [])}
print("on" if "week" in a and a["week"].get("enabled") is not False else "off")
PY
)
if [ "$start" = /apps/week ] && [ "$week" = on ] && [ -n "$have" ] && [ "$quiet" = quiet ]; then
  if [ -z "$SHA_WANT" ] || [ "$have" = "$SHA_WANT" ]; then say G "5 first screen: start page $have, Week app on, quiet layout"
  else say R "5 first screen: page $have is not the standard copy $SHA_WANT"; fi
else say R "5 first screen: start=$start, Week app ${week:-?}, page ${have:-missing}, layout $quiet"; fi

# 6 work first: the start page offers their daily work as presses (at least 3 starts into the chat)
asks=0; [ -n "$have" ] && asks=$(sudo grep -o '/cc?ask=' "$PAGE" | wc -l)
[ "$asks" -ge 3 ] && say G "6 work first: $asks starts on the page" || say R "6 work first: $asks starts on the page (3 or more)"

# 7 reasoner: a real one answers (their own ChatGPT or Claude seat, or a key), not only the small local model
seat=$(printf '%s' "$HEALTH" | python3 -c '
import sys,json
try: d=json.load(sys.stdin)
except Exception: print("bridge-down"); sys.exit()
c=d.get("codex") or {}; a=d.get("auth") or {}
print("codex" if c.get("signedIn") else ("claude" if a.get("loggedIn") else "none"))' 2>/dev/null)
k=$(sudo grep -cE '^(ANTHROPIC_API_KEY|OPENAI_API_KEY|OPENROUTER_API_KEY|GROQ_API_KEY)=.{8,}' "$D/.env" 2>/dev/null)
{ [ "$seat" = codex ] || [ "$seat" = claude ] || [ "${k:-0}" -gt 0 ]; } && say G "7 reasoner: seat $seat, keys $k" || say R "7 reasoner: seat $seat, keys ${k:-0} (the member signs in once)"

# 8 their past is inside: something of theirs beyond the seed (chats, files from the computer)
DOCS=$(cd "$D" && sudo docker compose exec -T api python - </dev/null 2>/dev/null <<'PY'
import os, requests
H={"X-Api-Key": os.environ.get("BRAIN_API_KEY","")}
d=requests.get("http://localhost:8000/documents?limit=2000", headers=H, timeout=30).json().get("documents") or []
n=lambda x: (x.get("name") or x.get("filename") or "")
chats=sum(1 for x in d if n(x).split("_")[0] in ("chatgpt","claude","claude-project","gemini","codex","claude-code","deepseek","grok","copilot","lechat","perplexity","pasted"))
laptop=sum(1 for x in d if n(x).startswith("laptop/"))
print(len(d), chats, laptop)
PY
)
read -r nd nc nl <<<"${DOCS:-? ? ?}"
[ "${nc:-0}" != "?" ] && [ $(( ${nc:-0} + ${nl:-0} )) -gt 0 ] && say G "8 their past: $nd documents, $nc chats, $nl from the computer" || say R "8 their past: ${nd} documents, ${nc} chats, ${nl} from the computer (bring the ChatGPT export or run Bring in this computer)"

# 9 move-in doors: the computer line and the chats card work from outside the login
dl=$(curl -s -o /dev/null -w '%{http_code}' -m 15 "localhost:$P/laptop/agent.sh")
cad=$(sudo awk -v hn="$HOSTNAMES" 'index($0, hn) && /\{/ {inb=1} inb && /import-laptop\/check/ {c++} inb && /^}/ {inb=0} END {print c+0}' /etc/caddy/Caddyfile 2>/dev/null)
[ "$dl" = 200 ] && [ "${cad:-0}" -gt 0 ] && say G "9 move-in doors: agent.sh $dl, Caddy opens the token paths" || say R "9 move-in doors: agent.sh $dl, Caddy token paths ${cad:-0} (docs/IMPORT.md 'The way in from the laptop')"

# 10 AI history: the Codex and Claude Code sessions on their computer come along (MEMBERS-11)
grep -q 'claude-code' "$D/scripts/import_chats.py" 2>/dev/null && grep -q 'Codex history' "$D/scripts/import/brain_import.py" 2>/dev/null \
  && say G "10 AI history: Codex and Claude Code sessions in the move-in" || say R "10 AI history: not in this code yet (branch members-11)"

# 11 used: the member (or the operator testing for them) has had turns in the console
th=$(sudo sh -c "cat '$CCH/.cc-bridge/turns.jsonl' 2>/dev/null | wc -l" | tr -dc 0-9)
[ "${th:-0}" -gt 0 ] && say G "11 used: $th console turns (operator tests count too)" || say R "11 used: no console turn yet (link and password not sent, or not opened)"

echo "SUM  $m: $g green, $r red"
