#!/usr/bin/env bash
# scripts/cc/init-world.sh
# Created: 2026-10-12
# Opens the world of a new brain: copies templates/world/ onto the box, fills the
# placeholders from the interview's answers file, makes it a git repository with one
# first commit, and (optionally) points the bridge at it. The world is the third layer
# on every box (engine, owner state, world; docs/brainfoundry/world-template.md): the
# engine's Update refreshes templates/world/, the person's world is never touched again.
#
# Seed-once, never clobbers: a target that already holds a .git (or any file) is left
# as it is and the script exits 0 saying so. Rerunning is safe.
#
#   bash scripts/cc/init-world.sh                                  -> /home/hands/world (or $CC_WORLD_DIR), no answers
#   bash scripts/cc/init-world.sh --answers ~/in/anne_interview.json --owner hands
#   bash scripts/cc/init-world.sh --target /tmp/w --answers a.json --persona-out /tmp/persona.md
#   bash scripts/cc/init-world.sh --wire                           -> also sets CC_WORLD_DIR and CC_WORK_DIR in the
#                                                                     bridge env and restarts cc-bridge (needs sudo)
#
# Options
#   --target DIR        where the world goes. Default: $CC_WORLD_DIR, else /home/${CC_HANDS_USER:-hands}/world
#   --answers FILE      the interview form's "Save as JSON" export (ops/brain-interview/common-interview.html,
#                       v2..v5 record: person, date, answers{A1..D13, A8_<perm>, B12_*, ...}, devices[], storage[]).
#                       Without it every placeholder reads "(fill in)".
#   --owner USER        chown the world to this user when run as root (the hands user on a split box)
#   --persona-out PATH  write the brain's persona file once from ME.md's one line (skipped if PATH exists).
#                       On a box: $BRAIN_DIR/api/brain_persona.local.md. The console owns it afterwards.
#   --git-name / --git-email   identity for the first commit. Default: the person's name, world@<hostname>
#   --date YYYY-MM-DD   the opening date (default today; tests pin it)
#   --wire              set CC_WORLD_DIR and CC_WORK_DIR to the target in the bridge env and restart cc-bridge
#   --template DIR      another template folder (default: templates/world beside this script's repo)
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
BRAIN_DIR=${BRAIN_DIR:-$(cd "$HERE/../.." && pwd)}
TEMPLATE="$BRAIN_DIR/templates/world"
TARGET=""
ANSWERS=""
OWNER=""
PERSONA_OUT=""
GIT_NAME=""
GIT_EMAIL=""
OPEN_DATE=$(date +%Y-%m-%d)
WIRE=0
BRIDGE_USER=${BRIDGE_USER:-cc}

while [ $# -gt 0 ]; do
    case "$1" in
    --target) TARGET=$2; shift 2 ;;
    --answers) ANSWERS=$2; shift 2 ;;
    --owner) OWNER=$2; shift 2 ;;
    --persona-out) PERSONA_OUT=$2; shift 2 ;;
    --git-name) GIT_NAME=$2; shift 2 ;;
    --git-email) GIT_EMAIL=$2; shift 2 ;;
    --date) OPEN_DATE=$2; shift 2 ;;
    --wire) WIRE=1; shift ;;
    --template) TEMPLATE=$2; shift 2 ;;
    -h|--help) sed -n '2,32p' "$0"; exit 0 ;;
    *) echo "unknown option: $1 (see --help)"; exit 1 ;;
    esac
done

[ -n "$TARGET" ] || TARGET=${CC_WORLD_DIR:-/home/${CC_HANDS_USER:-hands}/world}
[ -d "$TEMPLATE" ] || { echo "no template at $TEMPLATE"; exit 1; }
[ -f "$TEMPLATE/CLAUDE.md" ] || { echo "template at $TEMPLATE has no CLAUDE.md"; exit 1; }
if [ -n "$ANSWERS" ] && [ ! -f "$ANSWERS" ]; then echo "answers file not found: $ANSWERS"; exit 1; fi

# 1. never clobber: an existing world (or anything at the path) is left alone
if [ -d "$TARGET/.git" ]; then
    echo "world already open at $TARGET ($(git -C "$TARGET" log --oneline -1 2>/dev/null | cut -c1-60)); nothing done"
    exit 0
fi
if [ -e "$TARGET" ] && [ -n "$(ls -A "$TARGET" 2>/dev/null)" ]; then
    echo "$TARGET exists and is not empty but is not a world (no .git); refusing to write into it"
    exit 2
fi

# 2. copy the template
mkdir -p "$TARGET"
cp -R "$TEMPLATE/." "$TARGET/"
echo "copied templates/world -> $TARGET"

# 3. fill the placeholders from the answers (and seed the persona once)
FILL_OUT=$(python3 - "$TARGET" "$ANSWERS" "$OPEN_DATE" "$PERSONA_OUT" "$BRAIN_DIR" <<'PY'
import json, os, re, sys
from pathlib import Path

target, answers_path, open_date, persona_out, brain_dir = sys.argv[1:6]
root = Path(target)
FILL = "(fill in)"

state = {}
if answers_path:
    with open(answers_path, encoding="utf-8") as fh:
        state = json.load(fh)
if not isinstance(state, dict):
    state = {}
A = state.get("answers") if isinstance(state.get("answers"), dict) else {}

def one(v):
    """One line, trimmed; empty -> ''."""
    if v is None:
        return ""
    s = str(v).strip()
    return re.sub(r"\s*[\r\n]+\s*", "; ", s)

def a(key):
    return one(A.get(key))

def slug(s, default):
    s = re.sub(r"[^a-z0-9]+", "-", one(s).lower()).strip("-")
    return s[:24].rstrip("-") or default

PERM_LABEL = {"allowed": "allowed", "ask": "ask me first", "never": "never"}
JOIN_LABEL = {"joins": "yes", "ask": "ask me first", "outside": "no"}
PURPOSE_AREA = {
    "their own mind": "mind", "a teacher": "study", "a health guide": "health",
    "a private counsellor": "counsel", "a character": "character", "the memory of someone": "memory",
}

person = one(state.get("person"))
purpose_raw = a("B1")
if purpose_raw == "other" or (not purpose_raw and a("B1_other")):
    purpose = a("B1_other")
    first_area = slug(purpose, "general")
else:
    purpose = purpose_raw
    first_area = PURPOSE_AREA.get(purpose_raw, slug(purpose_raw, "general"))
if a("B1_other") and purpose_raw and purpose_raw != "other":
    purpose = purpose_raw + " (" + a("B1_other") + ")"

lang = a("B12_lang") or a("A10_lang")
work = a("A10_work")
pairs = [a("B10_%d" % i) for i in range(1, 7)]
pairs_txt = ", ".join(p if p and p != "any" else ("don't care" if p == "any" else "-") for p in pairs) if any(pairs) else ""

def persona_line():
    if not (person or work or lang or purpose):
        return ""
    parts = []
    head = person or "The person"
    if work and lang:
        parts.append(f"{head} is {work}, {lang} speaker.")
    elif work:
        parts.append(f"{head} is {work}.")
    elif lang:
        parts.append(f"{head} is a {lang} speaker.")
    else:
        parts.append(f"{head}.")
    if purpose:
        parts.append(f"This brain is for: {purpose}.")
    how = []
    if a("B12_length"): how.append(a("B12_length") + " answers")
    if a("B12_tone"): how.append(a("B12_tone"))
    if a("B12_humour"): how.append("humour " + a("B12_humour"))
    if how:
        parts.append("Answer with " + ", ".join(how) + ", in the language they write in.")
    return " ".join(parts)

def device_rows():
    rows = []
    for d in state.get("devices") or []:
        if not (one(d.get("kind")) or one(d.get("model"))):
            continue
        name = " ".join(x for x in (one(d.get("kind")), one(d.get("model"))) if x)
        role = "compute" if one(d.get("local")) == "yes" else ""
        rows.append(f"| {name} | {one(d.get('system')) or ''} | {one(d.get('whose')) or ''} | {one(d.get('use')) or ''} | {JOIN_LABEL.get(one(d.get('join')), FILL)} | {FILL} | {role or FILL} |")
    for d in state.get("oldDevices") or []:
        if not (one(d.get("kind")) or one(d.get("model"))):
            continue
        name = " ".join(x for x in (one(d.get("kind")), one(d.get("model"))) if x) + " (not in use)"
        role = "compute" if one(d.get("local")) == "yes" else "store"
        rows.append(f"| {name} | {one(d.get('system')) or ''} | {one(d.get('whose')) or ''} | no longer | {JOIN_LABEL.get(one(d.get('join')), FILL)} | {FILL} | {role} |")
    for s in state.get("storage") or []:
        if not (one(s.get("name")) or one(s.get("size"))):
            continue
        rows.append(f"| {one(s.get('name')) or 'storage'} (storage, {one(s.get('size')) or 'size ?'}) | | | | {JOIN_LABEL.get(one(s.get('join')), FILL)} | files | source |")
    return "\n".join(rows) if rows else f"| {FILL} | | | | | | |"

values = {
    "PERSON": person,
    "DATE": open_date,
    "INTERVIEW_DATE": one(state.get("date")),
    "INTERVIEW_VERSION": one(state.get("version")),
    "PURPOSE": purpose,
    "FIRST_AREA": first_area,
    "WORK": work,
    "LANG": lang,
    "REEXPLAIN": a("A4"),
    "TALK_ABOUT": a("A7"),
    "LENGTH": a("B12_length"),
    "TONE": a("B12_tone"),
    "HUMOUR": a("B12_humour"),
    "TEXT_SIZE": a("B12_size"),
    "LIGHT_DARK": a("B9"),
    "COLOURS_WANT": a("B9_want"),
    "COLOURS_NEVER": a("B9_never"),
    "PAIRS": pairs_txt,
    "PLACE": a("B11"),
    "NEVER_TELL": a("A9"),
    "FENCE": a("B17"),
    "FIRST_APP": a("B17_first"),
    "FIRST_IN": a("B2"),
    "FIRST_WEEK": a("A11"),
    "WORKING_SIGN": a("A12"),
    "STOP_SIGNALS": a("A13"),
    "CONNECTED_APPS": a("B7"),
    "ALWAYS_ON": a("B21_candidate") or a("B21_on"),
    "NET_STEADY": a("B21_net"),
    "PERSONA_LINE": persona_line(),
    "DEVICE_ROWS": device_rows(),
    "APP_ROWS": "| (none yet) | | | |",
    "PERM_else": a("A8_else") or "nothing more",
}
for perm in ("read", "write", "send", "cal_see", "cal_change", "web", "remember", "spend", "post"):
    values["PERM_" + perm] = PERM_LABEL.get(a("A8_" + perm), "")

# the area folders: the first area from the interview, inbox too when mail is connected
areas = [first_area]
if re.search(r"\b(mail|e-mail|email|inbox)\b", a("B7"), re.I):
    areas.append("inbox")
for area in areas:
    d = root / "areas" / area
    (d / "notes").mkdir(parents=True, exist_ok=True)
    (d / "notes" / ".gitkeep").write_text("")
    what = f"The area \"{area}\": " + (purpose if area == first_area and purpose else
                                       ("mail and appointments the brain reads for the person" if area == "inbox" else FILL))
    goes_in = values["FIRST_IN"] if area == first_area else "what the person forwards or asks about"
    (d / "README.md").write_text(
        f"# {area}\n\n"
        f"Created: {open_date}. One of the areas this brain is for (areas/README.md).\n\n"
        f"## What this area is\n\n{what}\n\n"
        f"## What goes in\n\n{goes_in or FILL}\n\n"
        f"## What never goes in\n\n{values['FENCE'] or FILL}\n\n"
        f"## Notes\n\nDated notes in `notes/` (`<yyyy-mm-dd>_<topic>.md`, shape from journal/TEMPLATE.md).\n"
    )

# fill every {{KEY}} in every text file of the world
pat = re.compile(r"\{\{([A-Za-z0-9_]+)\}\}")
filled = 0
for p in sorted(root.rglob("*")):
    if not p.is_file() or ".git" in p.parts:
        continue
    try:
        text = p.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        continue
    def rep(m):
        global filled
        filled += 1
        v = values.get(m.group(1), "")
        return v if v else FILL
    new = pat.sub(rep, text)
    if new != text:
        p.write_text(new, encoding="utf-8")

# the persona, once: the brain's identity file from ME.md's one line
if persona_out:
    out = Path(persona_out)
    if out.exists():
        print(f"persona: {out} exists, left as it is")
    else:
        brain_name = (person + "'s brain") if person else "your brain"
        body = ""
        tpl = Path(brain_dir) / "api" / "brain_persona.template.md"
        try:
            sys.path.insert(0, brain_dir)
            from api.persona_tools import personalize_text  # type: ignore
            if tpl.exists():
                body = personalize_text(tpl.read_text(encoding="utf-8"), brain_name, person or "the owner")
        except Exception:
            body = ""
        if not body:
            body = f"You are {brain_name}, the personal brain of {person or 'the owner'}.\n"
        seed = [
            "", "## From the world (seeded once by init-world.sh on " + open_date + "; the console owns this file from now on, ME.md in the world owns the reasoner's view)",
            "", values["PERSONA_LINE"],
        ]
        if values["NEVER_TELL"]:
            seed.append("Never asked for, never kept: " + values["NEVER_TELL"] + ".")
        if values["FENCE"]:
            seed.append("Stays outside this brain, never imported: " + values["FENCE"] + ".")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(body.rstrip("\n") + "\n" + "\n".join(seed) + "\n", encoding="utf-8")
        print(f"persona: wrote {out}")

print(f"filled {filled} placeholders from {'answers ' + answers_path if answers_path else 'no answers (every placeholder reads \"(fill in)\")'}; areas: {', '.join(areas)}")
print("FIRST_AREA=" + first_area)
print("PERSON=" + person)
PY
)
echo "$FILL_OUT" | grep -v '^FIRST_AREA=\|^PERSON='
FIRST_AREA=$(echo "$FILL_OUT" | sed -n 's/^FIRST_AREA=//p')
PERSON=$(echo "$FILL_OUT" | sed -n 's/^PERSON=//p')

# 4. one git repository, one first commit, by exact path
[ -n "$GIT_NAME" ] || GIT_NAME=${PERSON:-the owner}
[ -n "$GIT_EMAIL" ] || GIT_EMAIL="world@$(hostname -s 2>/dev/null || echo box)"
git -C "$TARGET" init -q
git -C "$TARGET" symbolic-ref HEAD refs/heads/main 2>/dev/null || true
( cd "$TARGET" && find . -path ./.git -prune -o -type f -print | sed 's#^\./##' | sort | xargs -d '\n' git add -- )
git -C "$TARGET" -c user.name="$GIT_NAME" -c user.email="$GIT_EMAIL" commit -q -m "world: opened $OPEN_DATE"
echo "git: $(git -C "$TARGET" log --oneline -1)"

# 5. ownership (a split box: the world belongs to the hands, the bridge reads through the group)
if [ -n "$OWNER" ] && [ "$(id -u)" = 0 ]; then
    chown -R "$OWNER:$OWNER" "$TARGET"
    chmod -R g+rX "$TARGET"; chmod -R g+w "$TARGET"; find "$TARGET" -type d -exec chmod g+s {} +
    echo "owner: $OWNER"
elif [ -n "$OWNER" ]; then
    echo "owner: not root, $TARGET left owned by $(id -un) (run with sudo to chown to $OWNER)"
fi

# 6. the bridge: the laptop's shape, world and work the same path
if [ "$WIRE" = 1 ]; then
    BRIDGE_HOME=$(eval echo "~$BRIDGE_USER")
    ENV_FILE="$BRIDGE_HOME/.cc-bridge/env"
    if sudo test -f "$ENV_FILE"; then
        for k in CC_WORLD_DIR CC_WORK_DIR; do
            sudo sh -c "grep -v '^$k=' '$ENV_FILE' > '$ENV_FILE.tmp'; echo '$k=$TARGET' >> '$ENV_FILE.tmp'; mv '$ENV_FILE.tmp' '$ENV_FILE'; chown $BRIDGE_USER:$BRIDGE_USER '$ENV_FILE'; chmod 600 '$ENV_FILE'"
        done
        sudo systemctl restart cc-bridge 2>/dev/null && echo "bridge: CC_WORLD_DIR=CC_WORK_DIR=$TARGET, restarted" || echo "bridge: env set, restart failed (systemctl restart cc-bridge by hand)"
    else
        echo "bridge: no env at $ENV_FILE; set CC_WORLD_DIR and CC_WORK_DIR to $TARGET by hand"
    fi
fi

# 7. the tree and the D1 line, for the operator to read back
echo
echo "the world at $TARGET:"
( cd "$TARGET" && find . -path ./.git -prune -o -print | sed 's#^\./##; /^\.$/d' | sort | sed 's/^/  /' )
echo
grep '^- D1' "$TARGET/decisions.md"
