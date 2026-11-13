#!/usr/bin/env bash
# scripts/cc/install-piper.sh: free Russian speech on the box (VOICE-RU-1, created 2026-11-13).
# Run once per box, by the box's owner, from any brain checkout on it (needs sudo):
#     bash scripts/cc/install-piper.sh            # all four Russian voices
#     bash scripts/cc/install-piper.sh dmitri     # only the ones named
# What it does: a venv at /opt/piper/venv with piper-tts pinned to PIPER_VERSION (GPL-3.0, run by
# the bridge as a separate process, never imported), the voice models from rhasspy/piper-voices
# into /opt/piper/voices, each checked against its sha256 below, then ffmpeg from apt when missing
# (mp3 instead of wav), then a test sentence. Root-owned, world-readable: every member's bridge on
# the box shares it. A bridge picks it up on its next restart when its console speaks Russian and
# it has no ElevenLabs key (docs/VOICE.md). It touches no .env, no unit, no member.
# Needs python3-venv (apt install python3-venv). About 260 MB for four voices plus ~120 MB of venv.
# Rollback: sudo rm -rf /opt/piper   (bridges then have no voice again; restart them to update /cc/health)
set -euo pipefail

PIPER_VERSION=${PIPER_VERSION:-1.8.0}
DIR=${PIPER_DIR:-/opt/piper}
BASE=https://huggingface.co/rhasspy/piper-voices/resolve/main/ru/ru_RU
# voice  sha256 of .onnx  sha256 of .onnx.json   (measured 2026-11-13; licences in docs/VOICE.md)
SUMS="dmitri 9ed9941bac7373f2ec1be36627e0e71a349a59ca5522d4363fd50701db05193a b7ed744f65ec73deb57fc8e419a5db5c0c5532026cf1cd21247f75937b6fbee2
denis 879bc365cb14d1380e3f5ed6044162ccf54c99f6161871569b7f830aec3ce841 e4fb4ab60262d1ab802c8c39301976c4135e545bc834a33c6eedc1f764df3bd6
irina 8ff38212d23da300bbe3705c645e6e5b9475f0bfde01558eb17813e22acaaaaa c2ec28bb38e2b59e93b959b3e40348c1afebbd272f30fed5d41205d08e98a9d7
ruslan 72a5f88e0b20928064eb45d88e1daa21f8af62d18613580d32cbb4aed48dcf7f 706a4fb17bc304abd07809b552deae615e64dcbffbfbd09854ba37ca59e88117"

WANT=("$@")
[ ${#WANT[@]} -eq 0 ] && WANT=(dmitri denis irina ruslan)
for v in "${WANT[@]}"; do
    printf '%s\n' "$SUMS" | grep -q "^$v " || { echo "install-piper: no voice called $v (dmitri denis irina ruslan)" >&2; exit 2; }
done

echo "== venv $DIR/venv, piper-tts $PIPER_VERSION"
sudo install -d -o root -g root -m 755 "$DIR" "$DIR/voices"
[ -x "$DIR/venv/bin/python" ] || sudo python3 -m venv "$DIR/venv"
sudo "$DIR/venv/bin/pip" install -q --no-cache-dir "piper-tts==$PIPER_VERSION"

TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
for v in "${WANT[@]}"; do
    read -r _ s_onnx s_json < <(printf '%s\n' "$SUMS" | grep "^$v ")
    stem="ru_RU-$v-medium"
    for pair in "$stem.onnx:$s_onnx" "$stem.onnx.json:$s_json"; do
        f=${pair%%:*}; sum=${pair#*:}
        if [ -f "$DIR/voices/$f" ] && echo "$sum  $DIR/voices/$f" | sha256sum -c --quiet 2>/dev/null; then
            echo "   $f present"; continue
        fi
        curl -sfL -o "$TMP/$f" "$BASE/$v/medium/$f"
        echo "$sum  $TMP/$f" | sha256sum -c --quiet || { echo "install-piper: $f sha256 mismatch, not installed" >&2; exit 1; }
        sudo install -o root -g root -m 644 "$TMP/$f" "$DIR/voices/$f"
        echo "   $f installed"
    done
done

if ! command -v ffmpeg >/dev/null; then
    echo "== ffmpeg (apt), for mp3"
    sudo env DEBIAN_FRONTEND=noninteractive apt-get install -y -q ffmpeg >/dev/null || echo "   ffmpeg not installed; the bridge sends wav"
fi

echo "== test"
v=${WANT[0]}
n=$(echo "Доброе утро." | "$DIR/venv/bin/piper" -m "$DIR/voices/ru_RU-$v-medium.onnx" --output-raw 2>/dev/null | wc -c)
[ "$n" -gt 4000 ] || { echo "install-piper: $v said nothing ($n bytes)" >&2; exit 1; }
echo "install-piper: OK, $v spoke $n bytes; voices: $(ls "$DIR/voices" | sed -n 's/^ru_RU-\(.*\)-medium\.onnx$/\1/p' | tr '\n' ' ')"
echo "Next: restart each member's bridge (sudo systemctl restart cc-bridge-<m>); undo: sudo rm -rf $DIR"
