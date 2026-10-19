# scripts/cc/member.sh — one member's names and ports on a shared box (multi-instance).
# Created: 2026-10-19 (docs/MULTI_INSTANCE.md). Sourced, never run: install.sh, split-hands.sh,
# scripts/multi/add-member.sh. The bridge's twin is scripts/cc/cc_member.py (same math, tested together).
#
#   CC_MEMBER=<handle>  CC_MEMBER_N=<n>   member n's block: 8100+10n api, +1 ui, +2 nodeos,
#                                          +3 postgres, +4 public chat, +7 terminal, +8 bridge
# No CC_MEMBER: today's single brain, exactly (8010 3010 8001 54332 3020 7681 7682, units
# claude-tab and cc-bridge, hands user "hands", compose project from the directory name).

M_RESERVED="hbar cc hands root admin brain brains ollama caddy console www api test"

member_handle_ok() {  # a flat handle: lowercase, starts with a letter, 2 to 16 characters, no dash
    [[ "${1:-}" =~ ^[a-z][a-z0-9]{1,15}$ ]] || return 1
    case " $M_RESERVED " in *" $1 "*) return 1 ;; esac
}

member_block_ok() { [[ "${1:-}" =~ ^[1-9][0-9]?$ ]]; }   # 1..99; 8100+990+8 stays under 9100

member_port() { echo $((8100 + 10 * $1 + $2)); }          # n offset

member_load() {  # sets the M_* names from CC_MEMBER / CC_MEMBER_N; returns 1 on a bad handle or block
    MEMBER=${CC_MEMBER:-}
    if [ -z "$MEMBER" ]; then
        M_N=""; M_SFX=""; M_PROJECT=""
        M_API_PORT=8010; M_UI_PORT=3010; M_NODEOS_PORT=8001; M_PG_PORT=54332
        M_PUBLIC_CHAT_PORT=3020; M_TERM_PORT=7681; M_CC_PORT=7682
        M_BRIDGE_USER=""; M_HANDS_USER=hands; M_TOKEN_VAR=CC_OPERATOR_TOKEN; M_CADDY_ENV=cc
        return 0
    fi
    member_handle_ok "$MEMBER" || { echo "bad member handle: $MEMBER (a-z0-9, 2-16, starts with a letter, not reserved)" >&2; return 1; }
    M_N=${CC_MEMBER_N:-}
    member_block_ok "$M_N" || { echo "member $MEMBER needs CC_MEMBER_N, a port block 1..99 (got '${M_N}')" >&2; return 1; }
    M_SFX="-$MEMBER"; M_PROJECT="brain-$MEMBER"
    M_API_PORT=$(member_port "$M_N" 0); M_UI_PORT=$(member_port "$M_N" 1)
    M_NODEOS_PORT=$(member_port "$M_N" 2); M_PG_PORT=$(member_port "$M_N" 3)
    M_PUBLIC_CHAT_PORT=$(member_port "$M_N" 4); M_TERM_PORT=$(member_port "$M_N" 7)
    M_CC_PORT=$(member_port "$M_N" 8)
    M_BRIDGE_USER="$MEMBER-cc"; M_HANDS_USER="$MEMBER-hands"
    M_TOKEN_VAR="CC_OPERATOR_TOKEN_${MEMBER^^}"; M_CADDY_ENV="cc-$MEMBER"
}
