#!/usr/bin/env bash
# brain-write: write stdin into ONE file of the brain repository, as root, for the CC bridge
# user. Installed by scripts/cc/install.sh to /usr/local/bin/brain-write with the repo path
# baked in. Refuses secrets (.env*), git internals (.git/), absolute paths and "..".
# Created 2026-09-20.
set -euo pipefail
REPO="__BRAIN_DIR__"
rel=${1:?usage: brain-write <path relative to the brain repo>  < content}
case "$rel" in
    /*|*..*|.env*|*/.env*|.git|.git/*|*/.git/*) echo "refused: $rel" >&2; exit 2 ;;
esac
dst="$REPO/$rel"
mkdir -p "$(dirname "$dst")"
tmp=$(mktemp "$dst.XXXXXX")
cat > "$tmp"
chown "$(stat -c %U:%G "$REPO")" "$tmp"
chmod 644 "$tmp"
mv -f "$tmp" "$dst"
echo "wrote $rel ($(wc -c < "$dst") bytes)"
