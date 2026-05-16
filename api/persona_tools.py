"""Persona personalization — single source of truth.

Shared by:
  - the API endpoint POST /persona/personalize (console "name your brain" flow)
  - scripts/personalize_persona.py (provisioner / manual-clone helper)

Both used to carry their own copy of the substitution logic. They now call
into this module so the banner-stripping + placeholder rules can never drift.
"""
import re

# Placeholders the brand template ships with. A persona is "configured" once
# none of these remain in the text.
PLACEHOLDER_TOKENS = ("[BRAIN_NAME]", "[OWNER_NAME]")


def detect_placeholders(text: str) -> list:
    """Return the known placeholder tokens still present in `text`."""
    return [tok for tok in PLACEHOLDER_TOKENS if tok in (text or "")]


def is_template(text: str) -> bool:
    """True while the persona still carries the unedited TEMPLATE banner."""
    return (text or "").lstrip().startswith("# TEMPLATE")


def is_configured(text: str) -> bool:
    """A persona counts as configured once no placeholders remain and the
    TEMPLATE banner has been stripped."""
    return not detect_placeholders(text) and not is_template(text)


def personalize_text(text: str, brain_name: str, owner_name: str) -> str:
    """Return `text` with the TEMPLATE banner + [CONFIGURE: ...] advisory block
    stripped and [BRAIN_NAME]/[OWNER_NAME] substituted.

    Pure function — no file IO. Idempotent: running it on already-personalized
    text is a no-op (no banner, no placeholders left to touch).
    """
    lines = text.split("\n")

    # Strip the TEMPLATE banner: leading comment lines + one trailing blank.
    if lines and lines[0].startswith("# TEMPLATE"):
        end = 0
        for i, line in enumerate(lines):
            if line.startswith("#"):
                end = i + 1
            else:
                break
        while end < len(lines) and not lines[end].strip():
            end += 1
        lines = lines[end:]
    text = "\n".join(lines)

    # Strip the [CONFIGURE: ...] advisory block (may span multiple lines).
    text = re.sub(r"\n*\[CONFIGURE:[^\]]*\]\n*", "\n\n", text, flags=re.DOTALL)

    # Substitute the real values.
    text = text.replace("[BRAIN_NAME]", brain_name)
    text = text.replace("[OWNER_NAME]", owner_name)
    return text
