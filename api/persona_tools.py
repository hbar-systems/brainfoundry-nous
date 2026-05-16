"""Persona personalization — single source of truth.

Shared by:
  - the API endpoint POST /persona/personalize (console "name your brain" flow)
  - scripts/personalize_persona.py (provisioner / manual-clone helper)

Both used to carry their own copy of the substitution logic. They now call
into this module so the banner-stripping + placeholder rules can never drift.

Track J1 — the persona is split across two files:
  - brain_persona.template.md  tracked, always the blank [BRAIN_NAME] template
  - brain_persona.local.md     gitignored, holds the personalized identity
The runtime loads .local.md if present, else .template.md. This keeps a
`git pull` (Track J) from ever overwriting a brain's identity.
"""
import re
from pathlib import Path

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


def migrate_legacy_persona(template_path, local_path, legacy_path) -> str:
    """One-time Track-J1 migration of a pre-J1 brain.

    Before J1 the persona lived in a single tracked file (`legacy_path`,
    api/brain_persona.md) and the personalize feature wrote the owner's real
    identity straight into it. J1 split that into a tracked blank template and
    a gitignored `brain_persona.local.md`. This moves an already-personalized
    legacy file into `local_path` so a later `git pull` cannot clobber the
    identity — the exact failure J1 exists to prevent.

    Idempotent. Safe to run on every startup. Returns one of:
      'skip-local-exists'  — already migrated (or freshly personalized)
      'skip-no-legacy'     — fresh post-J1 brain, no legacy file
      'removed-redundant'  — legacy file was just an un-personalized template
      'migrated'           — legacy identity preserved into local_path
    """
    template_path = Path(template_path)
    local_path = Path(local_path)
    legacy_path = Path(legacy_path)

    # Already have a personalized local file — nothing to do.
    if local_path.exists():
        return "skip-local-exists"
    # No legacy file — fresh post-J1 brain.
    if not legacy_path.exists():
        return "skip-no-legacy"

    try:
        legacy_text = legacy_path.read_text(encoding="utf-8")
    except Exception:
        return "skip-no-legacy"

    template_text = ""
    try:
        template_text = template_path.read_text(encoding="utf-8")
    except Exception:
        pass

    if legacy_text.strip() == template_text.strip():
        # Legacy file is just an un-personalized copy of the template — it
        # carries no identity. Remove the redundant (now untracked) file.
        try:
            legacy_path.unlink()
        except Exception:
            pass
        return "removed-redundant"

    # Legacy file is personalized — preserve it as the gitignored local copy,
    # then remove the legacy file only once the new copy is confirmed on disk.
    local_path.write_text(legacy_text, encoding="utf-8")
    try:
        if local_path.read_text(encoding="utf-8") == legacy_text:
            legacy_path.unlink()
    except Exception:
        pass
    return "migrated"
