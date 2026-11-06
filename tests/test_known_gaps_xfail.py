"""Known security gaps, pinned as strict xfail tests (2026-11-03).

Each test asserts the SAFE behaviour and fails today because the gap named in
THREAT_MODEL.md section 6 (and ops ideas line "deep_research + MCP bypass dispatch()")
exists. xfail(strict=True) means: the suite stays green now, and the day someone
fixes the gap the test XPASSes and the suite goes red until the marker is removed.
That is the signal to delete the xfail and the gap entry in THREAT_MODEL.md.

These are static source checks (no network, no model, no DB), so they are cheap and
cannot flake. They check the shape of the fix (one chokepoint), not an exact string.
"""
import os
import re

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


@pytest.mark.xfail(strict=True, reason=(
    "THREAT_MODEL gap: deep_research (api/research.py) calls web_search.run / "
    "fetch_url.run directly and skips api.tools.dispatch(), so it skips the egress "
    "guard, tier gate, budget cap and tool audit. Fix: route through dispatch()."))
def test_deep_research_goes_through_dispatch():
    src = _read("api/research.py")
    assert not re.search(r"\b(web_search|fetch_url)\.run\(", src), \
        "deep_research must not call tool .run() directly"
    assert "dispatch(" in src


@pytest.mark.xfail(strict=True, reason=(
    "THREAT_MODEL gap 6: _agentic_dispatch in api/main.py sends mcp__* names straight "
    "to mcp_client.call, skipping is_blocked_tool, egress scan, budget and audit. "
    "Fix: route MCP through api.tools.dispatch()."))
def test_mcp_calls_pass_a_governance_gate():
    src = _read("api/main.py")
    m = re.search(r'isinstance\(name, str\) and name\.startswith\("mcp__"\):\n((?:(?!\n\s*return await _mcp\.call).)*)\n\s*return await _mcp\.call', src, re.S)
    assert m, "MCP branch of _agentic_dispatch not found (code moved; update this test)"
    branch = m.group(1)
    assert re.search(r"dispatch\(|is_blocked_tool|scan_outbound|egress", branch), \
        "MCP branch calls the server with no gate"


@pytest.mark.xfail(strict=True, reason=(
    "THREAT_MODEL gap 5: fetch_url validates the resolved IP but httpx re-resolves at "
    "connect time, so a low-TTL DNS record can rebind to an internal address. "
    "Fix: pin the connection to the validated IP (custom transport)."))
def test_fetch_url_pins_validated_ip():
    src = _read("api/tools/fetch_url.py")
    assert re.search(r"transport|local_address|resolve_override|pinned", src, re.I), \
        "fetch_url has no connection pinning to the validated address"


# ── SEC-1 Warden 1, poisoned input (2026-11-06) ─────────────────────────────

@pytest.mark.xfail(strict=True, reason=(
    "SEC-1 gap: /integrations/telegram/webhook pins the FIRST chat that messages the bot "
    "as the owner (trust on first use). Between connect and the owner's first message, "
    "anyone who finds the bot's @username becomes the owner and gets answers from memory. "
    "Fix: a one-time pairing code shown in the console, required in the first message."))
def test_telegram_owner_pin_needs_a_pairing_code():
    src = _read("api/main.py")
    m = re.search(r"if owner is None:\n(.*?)\n\s*if chat_id != owner:", src, re.S)
    assert m, "telegram owner-pin block not found (code moved; update this test)"
    assert re.search(r"pair|code|nonce", m.group(1), re.I), \
        "the first chat becomes owner with no pairing check"


@pytest.mark.xfail(strict=True, reason=(
    "SEC-1 gap: federation DM /receive verifies the signature against the sender's OWN "
    "from_pubkey, so any sender can claim any from_brain (T1, named in the module docstring). "
    "Display only today (no reasoner, no memory), but the inbox shows a forged peer name. "
    "Fix: look the sender up in known_peers and verify against the pinned key."))
def test_dm_receive_verifies_against_pinned_peer():
    src = _read("api/federation_dm.py")
    m = re.search(r"async def receive_dm\(.*?\n(?=@router)", src, re.S)
    assert m, "receive_dm not found (code moved; update this test)"
    assert re.search(r"find_peer|known_peers|pinned", m.group(0).split('"""', 2)[-1]), \
        "receive_dm trusts the sender-supplied public key"


@pytest.mark.xfail(strict=True, reason=(
    "SEC-1 gap: the kernel 'remember' command (api/hbar_commands.py) inserts into "
    "document_embeddings with no injection scan and no mem_type/provenance stamp, unlike "
    "every other write lane (THREAT_MODEL section 6.3). Operator key + permit only, and the "
    "row has no embedding, but reembed_null_embeddings.py would make it retrievable untyped. "
    "Fix: run main._scan_and_classify_write (or classify_write) before the INSERT."))
def test_kernel_remember_is_scanned_and_stamped():
    src = _read("api/hbar_commands.py")
    m = re.search(r'if cmd == "remember":(.*?)\n    if cmd == "recall":', src, re.S)
    assert m, "remember branch not found (code moved; update this test)"
    assert re.search(r"scan_text|classify_write|_scan_and_classify_write|mem_type", m.group(1))
