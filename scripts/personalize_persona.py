#!/usr/bin/env python3
"""Personalize brain_persona.md for a specific operator.

Substitutes [BRAIN_NAME] and [OWNER_NAME] placeholders with real values, and
strips the TEMPLATE banner + [CONFIGURE: ...] advisory blocks so the brain
stops complaining about unfilled placeholders on day one.

Used by:
  - brainfoundry-provisioner during automated provisioning (Model 2B)
  - manual self-serve operators (Model 2A) running this script after clone

Usage:
  python scripts/personalize_persona.py --brain-name "Hbar" --owner-name "Yury"
"""
import argparse
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PERSONA_PATH = REPO_ROOT / "api" / "brain_persona.md"


def personalize(brain_name: str, owner_name: str) -> None:
    if not PERSONA_PATH.exists():
        raise SystemExit(f"persona file not found at {PERSONA_PATH}")

    text = PERSONA_PATH.read_text()

    # Strip TEMPLATE banner if present (first 4 comment lines + 1 blank line).
    lines = text.split("\n")
    if lines and lines[0].startswith("# TEMPLATE"):
        # Find the end of the banner: skip leading comment lines + one blank
        end = 0
        for i, line in enumerate(lines):
            if line.startswith("#"):
                end = i + 1
            else:
                break
        # Also drop trailing blank line after banner
        while end < len(lines) and not lines[end].strip():
            end += 1
        lines = lines[end:]
    text = "\n".join(lines)

    # Strip [CONFIGURE: ...] advisory block (multi-line, may contain newlines)
    text = re.sub(r"\n*\[CONFIGURE:[^\]]*\]\n*", "\n\n", text, flags=re.DOTALL)

    # Substitute the real placeholders
    text = text.replace("[BRAIN_NAME]", brain_name)
    text = text.replace("[OWNER_NAME]", owner_name)

    PERSONA_PATH.write_text(text)
    print(f"✓ personalized {PERSONA_PATH.name} for brain='{brain_name}', owner='{owner_name}'")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--brain-name", required=True, help="Display name of the brain (e.g., 'Hbar')")
    parser.add_argument("--owner-name", required=True, help="Owner's first name (e.g., 'Yury')")
    args = parser.parse_args()
    personalize(args.brain_name, args.owner_name)
