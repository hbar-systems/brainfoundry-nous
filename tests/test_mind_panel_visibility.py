"""
Regression guard for the "panel un-closable during onboarding" bug.

Root cause shipped in c8d3918: `const mindPanelOpen = onboardingActive ||
mindPanelShown` forced the panel open on any fresh brain (corpus <
ONBOARDING_CORPUS_THRESHOLD), so the user's ✕ / toggle — which only set
mindPanelShown — could never close it.

There is no JS test runner in this repo, so (as with test_compose_onboarding_env)
this asserts the invariant at the source level: panel VISIBILITY must depend on
mindPanelShown alone (a dismiss always wins), while first-run still auto-shows by
setting that same user-controlled flag.
"""
import os
import re

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _chat_js() -> str:
    return open(os.path.join(ROOT, "ui/pages/chat.js")).read()


def test_panel_visibility_does_not_depend_on_onboarding_active():
    src = _chat_js()
    m = re.search(r"const\s+mindPanelOpen\s*=\s*([^\n]+)", src)
    assert m, "mindPanelOpen definition not found in chat.js"
    rhs = m.group(1)
    # The exact bug pattern must be gone, and onboardingActive must not gate
    # visibility (it would override the user's dismiss → un-closable panel).
    assert "onboardingActive" not in rhs, (
        "mindPanelOpen must not depend on onboardingActive: " + rhs.strip()
    )
    assert "mindPanelShown" in rhs
    assert "onboardingActive || mindPanelShown" not in src


def test_first_run_auto_shows_panel_via_user_controlled_flag():
    src = _chat_js()
    # Within the onboarding-status handler, first-run must auto-show the panel by
    # setting the SAME flag the ✕/toggle control, so the wow is preserved AND the
    # user can still close it.
    start = src.index("fetch('/api/bf/onboarding/status')")
    block = src[start:start + 900]
    assert "setOnboardingActive(true)" in block, "onboarding-status block not found"
    assert "setMindPanelShown(true)" in block, (
        "first-run must auto-show the panel via setMindPanelShown(true)"
    )
    # And the dismiss path flips that same flag off.
    assert "setMindPanel(false)" in src
