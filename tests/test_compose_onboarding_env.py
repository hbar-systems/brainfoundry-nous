"""
Regression guard: every onboarding/trial env var the code reads MUST be wired
into the docker-compose api service `environment:` block.

The api service uses an explicit allow-list (not env_file), so a var that the
onboarding code reads but compose doesn't pass never reaches the container —
which is exactly how the first cut shipped dead-on-arrival in production
(TRIAL_REASONER_API_KEY set in .env but never forwarded). This test derives the
required set by scanning the source for getenv-style reads of TRIAL_*/ONBOARDING_*
names, so adding a new onboarding env var without wiring compose fails CI.
"""
import os
import re

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# Files that read onboarding/trial configuration from the environment.
_SOURCE_FILES = [
    "api/onboarding/trial_reasoner.py",
    "api/onboarding/core.py",
    "api/settings_store.py",
]

# Matches os.getenv("NAME" / _env("NAME" / _int_env("NAME" — i.e. an actual
# env read, not a Python constant that merely shares the prefix.
_ENV_READ = re.compile(r'(?:os\.getenv|_env|_int_env)\(\s*["\']([A-Z_][A-Z0-9_]*)["\']')


def _required_env_vars() -> set:
    found = set()
    for rel in _SOURCE_FILES:
        src = open(os.path.join(ROOT, rel)).read()
        for name in _ENV_READ.findall(src):
            if name.startswith("TRIAL_") or name.startswith("ONBOARDING_"):
                found.add(name)
    return found


def _compose_api_env_vars() -> set:
    text = open(os.path.join(ROOT, "docker-compose.yml")).read()
    # Slice the api service block: from "\n  api:\n" to the next 2-space-indented
    # top-level key (next service) or EOF.
    m = re.search(r"\n  api:\n(.*?)(?=\n  [\w-]+:\n|\Z)", text, re.S)
    assert m, "could not locate the api service block in docker-compose.yml"
    api_block = m.group(1)
    return set(re.findall(r"^\s*-\s*([A-Z_][A-Z0-9_]*)=", api_block, re.M))


def test_onboarding_env_vars_wired_into_compose():
    required = _required_env_vars()
    # Sanity: the nine known vars must be discovered (guards the regex itself).
    assert "TRIAL_REASONER_API_KEY" in required
    assert len(required) >= 9, f"expected >=9 onboarding env vars, found {sorted(required)}"

    wired = _compose_api_env_vars()
    missing = required - wired
    assert not missing, (
        "onboarding/trial env vars read by the code but NOT wired into the "
        f"docker-compose api environment: {sorted(missing)}"
    )
