"""
SEC-PASS-1 (2026-11-13), class of CVE-2026-70619: a route that changes server-wide state must
carry the owner key server-side. This sweep walks the live route table: every POST/PUT/PATCH/DELETE
route needs the owner dependency (get_api_key / _operator_auth) or the app-backend gate, unless it
is on the reviewed list of public doors below, each of which authenticates another way. A new
ungated mutating route fails here until someone reviews it and adds it with its reason.
"""
import os
import sys
import tempfile
import types

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
try:
    import sentence_transformers  # noqa: F401
except ImportError:
    _st = types.ModuleType("sentence_transformers")
    _st.SentenceTransformer = object
    sys.modules["sentence_transformers"] = _st

os.environ.setdefault("BRAIN_IDENTITY_SECRET", "test-only-secret")
_RUNTIME = tempfile.mkdtemp(prefix="sec-pass-1-")
os.environ.setdefault("BRAIN_RUNTIME_DIR", _RUNTIME)
os.environ.setdefault("SETTINGS_PATH", os.path.join(_RUNTIME, "settings.json"))

from fastapi.routing import APIRoute  # noqa: E402

from api import main as m  # noqa: E402

_GATES = {"get_api_key", "_operator_auth", "require_backend_caller"}

# Reviewed 2026-11-13. path -> how it authenticates instead of the owner key.
PUBLIC_DOORS = {
    "/v1/federation/assertion": "signed assertion verified against a PINNED peer key; replay cache",
    "/integrations/telegram/webhook": "per-bot secret token header; answers only the pinned owner chat",
    "/v1/public/chat": "public-scoped corpus only; Turnstile when configured; per-IP rate limit",
    "/v1/federation/query": "public-scoped corpus only, read-only; per-IP rate limit",
    "/v1/ask": "signed peer assertion; public-scoped chunks only; per-peer rate limit",
    "/documents/import-laptop/file": "one-run laptop-import bearer token minted by the owner",
    "/documents/import-laptop/finish": "one-run laptop-import bearer token minted by the owner",
    "/documents/import-laptop/check": "POST: the survey's inventory (names, sizes, dates; no content) under a survey-only one-run token minted by the owner; 64 MB cap, paths cleaned; MOVE-IN-2 2026-11-16, awaiting hbar's review",
    "/v1/federation/dm/receive": "ED25519 signature over the payload; size and rate bounds",
    "/harmonics/exchange": "contributor signature verified; receiver records its own row",
    "/harmonics/score": "scoring open; record=true checks the owner key in the handler (SEC-1)",
    "/submissions": "public contribution queue; the owner lists and decides with the key",
}


# Public GETs that hand out something to RUN on a person's computer. They change no state (so the sweep
# above does not see them) but they are a door of their own: what they serve runs with the person's rights.
# Reviewed list; a new ungated route serving a script fails here until it is reviewed and listed.
PUBLIC_SCRIPT_DOORS = {
    "/documents/import-laptop/helper.py": "the Python helper, static file from the image (2026-11-03)",
    "/laptop/agent.sh": "the dial-out agent for Mac and Linux, rendered from scripts/import/agent.sh with the never-send "
                        "rules of brain_import.py and the Host's address (validated); no key in the address, no state, "
                        "no-store; it only calls the four token paths; SPOKE-3 2026-11-16, awaiting hbar's review",
    "/laptop/agent.ps1": "the same agent for Windows PowerShell 5.1; SPOKE-3 2026-11-16, awaiting hbar's review",
}
SCRIPT_SUFFIXES = (".sh", ".ps1", ".py", ".bat", ".cmd", ".command", ".exe", ".pkg", ".dmg", ".msi", ".app")


def _dep_names(dependant, out):
    for d in dependant.dependencies:
        out.add(getattr(d.call, "__name__", type(d.call).__name__))
        _dep_names(d, out)
    return out


def test_every_mutating_route_is_owner_gated_or_a_reviewed_public_door():
    ungated = []
    for r in m.app.routes:
        if not isinstance(r, APIRoute) or not (r.methods & {"POST", "PUT", "PATCH", "DELETE"}):
            continue
        if _dep_names(r.dependant, set()) & _GATES:
            continue
        if r.path in PUBLIC_DOORS or r.path.rstrip("/") in PUBLIC_DOORS:
            continue
        ungated.append((sorted(r.methods), r.path))
    assert not ungated, f"mutating routes without the owner gate (review, then gate or list): {ungated}"


def test_settings_and_admin_routes_refuse_a_missing_key(monkeypatch):
    from fastapi.testclient import TestClient
    monkeypatch.setattr(m, "BRAIN_API_KEY", "test-api-key")
    c = TestClient(m.app)
    for path, body in (("/settings/model", {"model": "x"}), ("/settings/auto-update", {"enabled": True}),
                       ("/integrations/calendar/ics", {"url": "https://a.example/x.ics"}),
                       ("/integrations/mcp/connect", {"name": "x", "url": "http://127.0.0.1:1"}),
                       ("/admin/update", {}), ("/admin/revert", {})):
        r = c.post(path, json=body)
        assert r.status_code == 401, (path, r.status_code)
        r = c.post(path, json=body, headers={"X-API-Key": "wrong"})
        assert r.status_code == 401, (path, r.status_code)


def test_every_public_script_route_is_a_reviewed_door():
    found = []
    for r in m.app.routes:
        if not isinstance(r, APIRoute) or "GET" not in r.methods:
            continue
        if _dep_names(r.dependant, set()) & _GATES:
            continue
        if r.path.lower().endswith(SCRIPT_SUFFIXES):
            found.append(r.path)
    assert sorted(found) == sorted(PUBLIC_SCRIPT_DOORS), f"public routes serving something to run: {found}"
