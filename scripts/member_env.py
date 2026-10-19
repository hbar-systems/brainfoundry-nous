#!/usr/bin/env python3
"""member_env.py — write one member's .env on a shared box, fresh secrets into the file only.

Created 2026-10-19 for scripts/add-member.sh (docs/MULTI_INSTANCE.md). Starts from .env.example,
sets the member's names, compose project and port block, and fresh secrets. Nothing secret is
printed, logged or passed on a command line: the summary names keys, never values.

    python3 scripts/member_env.py <handle> <n> <template> <out>     # refuses an existing <out>
"""
from __future__ import annotations

import os
import re
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "cc"))
import cc_member  # noqa: E402

SECRET_KEYS = ("BRAIN_API_KEY", "BRAIN_IDENTITY_SECRET", "NODEOS_SIGNING_SECRET", "NODEOS_INTERNAL_KEY",
               "POSTGRES_PASSWORD", "JWT_SECRET")
KEYPAIR_KEYS = ("BRAIN_PRIVATE_KEY", "BRAIN_PUBLIC_KEY")


def member_values(handle: str, n) -> dict:
    """The member's non-secret settings: names, project, ports, its own checkout, the shared Ollama."""
    p = cc_member.ports(n)
    return {
        "BRAIN_ENV": "prod",
        "BRAIN_ID": handle,
        "BRAIN_NAME": f"{handle.capitalize()}'s Brain",
        "BRAIN_OWNER": handle.capitalize(),
        "COMPOSE_PROJECT_NAME": f"brain-{handle}",
        "BRAIN_API_PORT": str(p["api"]),
        "BRAIN_UI_PORT": str(p["ui"]),
        "BRAIN_NODEOS_PORT": str(p["nodeos"]),
        "BRAIN_POSTGRES_PORT": str(p["postgres"]),
        "BRAIN_PUBLIC_CHAT_PORT": str(p["public_chat"]),
        "API_BASE": f"http://localhost:{p['api']}",
        "BRAIN_HOST_DIR": f"/srv/brains/{handle}",
        "BRAIN_PUBLIC_URL": f"https://{handle}.brainfoundry.ai",
        "TRUST_PROXY_HEADERS": "true",
        "OLLAMA_URL": "http://ollama:11434",
        "BRAIN_CC_ENABLED": "true",
    }


def build(template: str, handle: str, n, token=lambda: secrets.token_hex(32), keypair=None) -> str:
    """The .env text. Template lines keep their place and comments; a set key replaces its line,
    a key the template lacks is appended. `keypair` () -> (private, public) or None to leave empty."""
    values = dict(member_values(handle, n))
    for k in SECRET_KEYS:
        values[k] = token()
    if keypair is not None:
        values.update(zip(KEYPAIR_KEYS, keypair()))
    out, seen = [], set()
    for line in template.splitlines():
        m = re.match(r"^([A-Z][A-Z0-9_]*)=", line)
        if m and m.group(1) in values and m.group(1) not in seen:
            out.append(f"{m.group(1)}={values[m.group(1)]}")
            seen.add(m.group(1))
        else:
            out.append(line)
    extra = [k for k in values if k not in seen]
    if extra:
        out += ["", f"# member {handle}, port block {n} (scripts/add-member.sh)"] + [f"{k}={values[k]}" for k in extra]
    return "\n".join(out) + "\n"


def _keypair():
    """The brain's federation keypair, when the host python has `cryptography`; else None."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from api.identity.core import generate_brain_keypair
        return generate_brain_keypair
    except Exception:
        return None


def main(argv) -> int:
    if len(argv) != 4:
        print(__doc__.strip().splitlines()[-1].strip(), file=sys.stderr)
        return 2
    handle, n, template, out = argv
    if not cc_member.handle_ok(handle) or not cc_member.block_ok(n):
        print(f"refused: bad handle or block ({handle!r}, {n!r})", file=sys.stderr)
        return 2
    if os.path.exists(out):
        print(f"refused: {out} exists; a member's .env is written once", file=sys.stderr)
        return 1
    kp = _keypair()
    text = build(Path(template).read_text(), handle, n, keypair=kp)
    fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(text)
    print(f"wrote {out} (mode 600): fresh {', '.join(SECRET_KEYS)}"
          + (", and the federation keypair" if kp else "; no federation keypair (host python lacks cryptography, see docs/MULTI_INSTANCE.md)"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
