#!/usr/bin/env python3
"""spoke_config.py: one member's spoke files on a shared box, from the handle and port block alone.
Created 2026-11-14 (SPOKE-2A). Standard library only. Design: docs/spoke.md section 10.

    python3 spoke_config.py ports   <handle> <block>                 the four ports, one per line
    python3 spoke_config.py config  <handle> <block> [--domain D]    Headscale config.yaml
    python3 spoke_config.py policy  <handle>                         Headscale policy (brain -> laptop:22 only)
    python3 spoke_config.py env     <handle> <block> [--domain D] [--console URL]   /etc/spoke/<m>.env
    python3 spoke_config.py caddy   <handle> <block> [--domain D]    the Caddy site block
    python3 spoke_config.py sudoers <handle> [--bridge-user U]       the one sudoers line, checked by visudo on apply
    python3 spoke_config.py write   <handle> <block> <dir> [...]     all of the above into <dir> (never /etc itself)

Ports (decided 2026-11-14, measured free on the box by spoke-install.sh before any apply):
  SOCKS of the brain's node   8100+10n+9   (the member block's spare +9, as SPOKE-1 planned)
  Headscale http              9100+10n     (a spoke block above every member block: 8100+990+8 < 9100)
  Headscale metrics           9100+10n+1
  Headscale grpc              9100+10n+2   (127.0.0.1 only; the CLI uses the unix socket)
Every port listens on 127.0.0.1 only; Caddy is the only way in, at spoke.<m>.<domain>.

The handle is the member's (a-z0-9, 2 to 16, starts with a letter). Unlike cc_member, "hbar" is allowed:
hbar's rehearsal brain on friends-1 is not a member but gets the first spoke.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
VERBS = ("status", "inventory", "plan", "apply", "undo", "leave", "organise", "fingerprint", "bundle", "move-in", "move-in-status")


def handle_ok(h: str) -> bool:
    return bool(re.fullmatch(r"[a-z][a-z0-9]{1,15}", h or ""))


def block_ok(n) -> bool:
    return bool(re.fullmatch(r"[1-9][0-9]?", str(n)))


def domain_ok(d: str) -> bool:
    return bool(re.fullmatch(r"[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+", d or ""))


def ports(n) -> dict:
    if not block_ok(n):
        raise ValueError(f"port block must be 1..99, got {n!r}")
    n = int(n)
    return {"socks": 8100 + 10 * n + 9, "hs_http": 9100 + 10 * n, "hs_metrics": 9100 + 10 * n + 1,
            "hs_grpc": 9100 + 10 * n + 2}


def names(h: str, domain: str = "brainfoundry.ai") -> dict:
    return {"door_user": f"{h}-spoke", "group": f"{h}-brain", "site": f"spoke.{h}.{domain}",
            "etc": f"/etc/headscale/{h}", "env": f"/etc/spoke/{h}.env", "var": f"/var/lib/spoke/{h}",
            "hs_state": f"/var/lib/headscale/{h}", "hs_sock": f"/run/headscale/{h}/headscale.sock",
            "ts_sock": f"/run/spoke/{h}/tailscaled.sock", "sudoers": f"/etc/sudoers.d/spoke-{h}"}


def config(h: str, n, domain: str = "brainfoundry.ai") -> str:
    """Headscale's config.yaml for 0.26 (unverified against a live 0.26 until the apply: the key names
    follow the 0.26 example config). No secrets in it: the noise key is a separate file in the state dir."""
    p, nm = ports(n), names(h, domain)
    return f"""# Headscale for {h}'s spoke network. Written by scripts/spoke/box/spoke_config.py (SPOKE-2A, 2026-11-14).
# One brain, one network: only {h}'s brain node and {h}'s own laptops ever join it.
server_url: https://{nm['site']}
listen_addr: 127.0.0.1:{p['hs_http']}
metrics_listen_addr: 127.0.0.1:{p['hs_metrics']}
grpc_listen_addr: 127.0.0.1:{p['hs_grpc']}
grpc_allow_insecure: false
noise:
  private_key_path: {nm['hs_state']}/noise_private.key
prefixes:
  v4: 100.64.0.0/10
  v6: fd7a:115c:a1e0::/48
  allocation: sequential
derp:
  server:
    enabled: false
  urls:
    - https://controlplane.tailscale.com/derpmap/default
  auto_update_enabled: true
  update_frequency: 24h
disable_check_updates: true
ephemeral_node_inactivity_timeout: 30m
database:
  type: sqlite
  sqlite:
    path: {nm['hs_state']}/db.sqlite
    write_ahead_log: true
log:
  level: info
  format: text
policy:
  mode: file
  path: {nm['etc']}/policy.json
dns:
  magic_dns: false
  base_domain: spoke-{h}.internal
  override_local_dns: false
  nameservers:
    global: []
unix_socket: {nm['hs_sock']}
unix_socket_permission: "0770"
logtail:
  enabled: false
randomize_client_port: false
"""


def policy(h: str) -> str:
    """The brain's node (tag:brain) may reach the laptops on port 22; the laptops reach nothing."""
    return json.dumps({
        "tagOwners": {"tag:brain": [f"{h}@"]},
        "acls": [{"action": "accept", "src": ["tag:brain"], "dst": [f"{h}@:22"]}],
    }, indent=2) + "\n"


def env(h: str, n, domain: str = "brainfoundry.ai", console: str = "") -> str:
    p, nm = ports(n), names(h, domain)
    console = console or f"https://console.{h}.{domain}"
    return "".join(f"{k}={v}\n" for k, v in (
        ("SPOKE_HANDLE", h), ("SPOKE_BLOCK", int(n)), ("SOCKS_PORT", p["socks"]), ("HS_HTTP_PORT", p["hs_http"]),
        ("HS_CONFIG", f"{nm['etc']}/config.yaml"), ("LOGIN_SERVER", f"https://{nm['site']}"),
        ("LOCAL_LOGIN_SERVER", f"http://127.0.0.1:{p['hs_http']}"), ("CONSOLE_URL", console)))


def _fill(template: str, values: dict) -> str:
    out = template
    for k, v in values.items():
        out = out.replace(f"@@{k}@@", str(v))
    if "@@" in out:
        raise ValueError("a placeholder was left: " + out[out.index("@@"):][:40])
    return out


def caddy(h: str, n, domain: str = "brainfoundry.ai") -> str:
    return _fill((HERE / "caddy-spoke.snippet").read_text(),
                 {"SITE": names(h, domain)["site"], "PORT": ports(n)["hs_http"], "HANDLE": h})


def sudoers(h: str, bridge_user: str = "") -> str:
    bridge_user = bridge_user or f"{h}-cc"
    if not re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}", bridge_user):
        raise ValueError(f"bad bridge user {bridge_user!r}")
    door = "/usr/local/sbin/spoke-door"
    cmds = [f"{door} {h} {v}" for v in ("status", "inventory", "plan", "apply", "leave", "fingerprint", "bundle")]
    cmds += [f"{door} {h} organise on", f"{door} {h} organise off"]
    # SWITCH-1 (2026-11-16): the app in the console's language, and the move-in over the spoke (its token on stdin)
    cmds += [f"{door} {h} bundle en", f"{door} {h} bundle ru", f"{door} {h} move-in", f"{door} {h} move-in-status"]
    # undo takes one id; spoke-door refuses anything that is not apply's own id shape
    cmds += [f"{door} {h} undo *"]
    return _fill((HERE / "sudoers-spoke.template").read_text(),
                 {"HANDLE": h, "BRIDGE": bridge_user, "DOOR_USER": f"{h}-spoke", "COMMANDS": ", ".join(cmds)})


def _opt(argv: list[str], name: str, default: str = "") -> str:
    return argv[argv.index(name) + 1] if name in argv and argv.index(name) + 1 < len(argv) else default


def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[0] not in ("ports", "config", "policy", "env", "caddy", "sudoers", "write"):
        print(__doc__.split("Ports")[0].strip(), file=sys.stderr)
        return 2
    cmd, h = argv[0], argv[1]
    if not handle_ok(h):
        print(f"refused: bad handle {h!r}", file=sys.stderr)
        return 2
    domain = _opt(argv, "--domain", "brainfoundry.ai")
    if not domain_ok(domain):
        print(f"refused: bad domain {domain!r}", file=sys.stderr)
        return 2
    console = _opt(argv, "--console")
    if console and not re.fullmatch(r"https://[a-z0-9.-]+(/[A-Za-z0-9._/-]*)?", console):
        print(f"refused: console must be a plain https URL, got {console!r}", file=sys.stderr)
        return 2
    try:
        if cmd == "policy":
            sys.stdout.write(policy(h)); return 0
        if cmd == "sudoers":
            sys.stdout.write(sudoers(h, _opt(argv, "--bridge-user"))); return 0
        if len(argv) < 3 or not block_ok(argv[2]):
            print("refused: need a port block 1..99", file=sys.stderr); return 2
        n = argv[2]
        if cmd == "ports":
            sys.stdout.write("".join(f"{k}\t{v}\n" for k, v in ports(n).items())); return 0
        if cmd == "config":
            sys.stdout.write(config(h, n, domain)); return 0
        if cmd == "env":
            sys.stdout.write(env(h, n, domain, console)); return 0
        if cmd == "caddy":
            sys.stdout.write(caddy(h, n, domain)); return 0
        if len(argv) < 4:
            print("refused: write needs a folder", file=sys.stderr); return 2
        out = Path(argv[3])
        if str(out.resolve()).startswith(("/etc", "/var", "/usr", "/run")):
            print("refused: write builds files in a staging folder; spoke-install.sh installs them", file=sys.stderr)
            return 2
        out.mkdir(parents=True, exist_ok=True)
        for name, text in (("config.yaml", config(h, n, domain)), ("policy.json", policy(h)),
                           ("spoke.env", env(h, n, domain, console)), ("Caddyfile.spoke", caddy(h, n, domain)),
                           ("sudoers", sudoers(h, _opt(argv, "--bridge-user")))):
            (out / name).write_text(text)
            print(out / name)
        return 0
    except ValueError as e:
        print(f"refused: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
