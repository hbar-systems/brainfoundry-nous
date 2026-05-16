#!/usr/bin/env python3
"""Personalize the brain persona for a specific operator.

Substitutes [BRAIN_NAME] and [OWNER_NAME] placeholders with real values, and
strips the TEMPLATE banner + [CONFIGURE: ...] advisory blocks so the brain
stops complaining about unfilled placeholders on day one.

Track J1 — reads the tracked blank template (api/brain_persona.template.md)
and writes the personalized result to api/brain_persona.local.md, which is
gitignored. The tracked template is never modified, so a `git pull` can never
overwrite the brain's identity.

The substitution logic lives in api/persona_tools.py — this script and the
console endpoint POST /persona/personalize both call into it, so the two
paths can never drift.

Used by:
  - brainfoundry-provisioner during automated provisioning (Model 2B)
  - manual self-serve operators (Model 2A) running this script after clone
  - (the console "name your brain" button runs the same logic via the API)

Usage:
  python scripts/personalize_persona.py --brain-name "Hbar" --owner-name "Yury"
"""
import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_PATH = REPO_ROOT / "api" / "brain_persona.template.md"
LOCAL_PATH = REPO_ROOT / "api" / "brain_persona.local.md"

# Make `api` importable when the script is run as `python scripts/...`.
sys.path.insert(0, str(REPO_ROOT))
from api.persona_tools import personalize_text  # noqa: E402


def personalize(brain_name: str, owner_name: str) -> None:
    if not TEMPLATE_PATH.exists():
        raise SystemExit(f"persona template not found at {TEMPLATE_PATH}")

    text = TEMPLATE_PATH.read_text()
    text = personalize_text(text, brain_name, owner_name)
    LOCAL_PATH.write_text(text)
    print(f"✓ wrote {LOCAL_PATH.name} for brain='{brain_name}', owner='{owner_name}' "
          f"(gitignored — the tracked template is untouched)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--brain-name", required=True, help="Display name of the brain (e.g., 'Hbar')")
    parser.add_argument("--owner-name", required=True, help="Owner's first name (e.g., 'Yury')")
    args = parser.parse_args()
    personalize(args.brain_name, args.owner_name)
