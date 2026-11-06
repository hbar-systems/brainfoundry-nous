#!/usr/bin/env python3
"""scripts/caddy_sites.py: drop whole site blocks from a Caddyfile by matching braces, not line counts.
Created: 2026-10-26 (scripts/remove-member.sh; docs/MULTI_INSTANCE.md "Removing a member", step 9).

    python3 scripts/caddy_sites.py list <Caddyfile> <site> [<site> ...]      the line ranges, changes nothing
    python3 scripts/caddy_sites.py drop <Caddyfile> <out> <site> [<site> ...] writes the rest to <out>
    python3 scripts/caddy_sites.py ports <Caddyfile> <port> [<port> ...]      the blocks that proxy to a port

"ports" (2026-11-06, docs/MEMBER_LIFECYCLE.md) finds a member's sites by its port block, whatever their
names (showcase-1 serves brain.hbar.university, not university.brainfoundry.ai): one line per block,
"<pure|mixed>\t<first address>\t<all addresses>\tlines a-b". Pure: every local upstream of the block
is one of the ports. Mixed: it also proxies elsewhere, so dropping it would cut another site.

A site block is a top-level line whose address list names <site> (exactly, comma or space separated),
ending in "{", up to its matching "}". Braces inside quotes or after "#" do not count. Exit 1 when a
named site is not found (list prints what was found), 2 on an unbalanced file."""
from __future__ import annotations

import re
import sys


def _depth_delta(line: str) -> int:
    d, q = 0, None
    for i, c in enumerate(line):
        if q:
            if c == q and line[i - 1] != "\\":
                q = None
        elif c in "\"`":
            q = c
        elif c == "#" and (i == 0 or line[i - 1].isspace()):
            break
        elif c == "{":                       # a {$VAR} or {host} placeholder closes on its own line
            d += 1
        elif c == "}":
            d -= 1
    return d


def blocks(text: str) -> list[tuple[list[str], int, int]]:
    """Top-level blocks: (addresses, first line index, last line index), 0-based, inclusive."""
    out, depth, start, addrs = [], 0, None, []
    for n, line in enumerate(text.splitlines()):
        d = _depth_delta(line)
        if depth == 0 and d > 0:
            start, addrs = n, line.split("{", 1)[0].replace(",", " ").split()
        depth += d
        if depth < 0:
            raise ValueError(f"unbalanced '}}' at line {n + 1}")
        if depth == 0 and start is not None:
            out.append((addrs, start, n))
            start = None
    if depth:
        raise ValueError("unbalanced '{' at end of file")
    return out


def find(text: str, sites: list[str]) -> list[tuple[str, int, int]]:
    return [(s, a, b) for addrs, a, b in blocks(text) for s in sites if s in addrs]


_UPSTREAM = re.compile(r"(?:localhost|127\.0\.0\.1|\[::1\]):(\d{2,5})\b")


def _uncommented(line: str) -> str:
    q = None
    for i, c in enumerate(line):
        if q:
            if c == q and line[i - 1] != "\\":
                q = None
        elif c in "\"`":
            q = c
        elif c == "#" and (i == 0 or line[i - 1].isspace()):
            return line[:i]
    return line


def by_ports(text: str, ports: list[str]) -> list[tuple[str, list[str], int, int]]:
    """Blocks with a local upstream on one of `ports`: (pure|mixed, addresses, first, last), 0-based."""
    want, lines, out = {str(int(p)) for p in ports}, text.splitlines(), []
    for addrs, a, b in blocks(text):
        ups = {m for ln in lines[a:b + 1] for m in _UPSTREAM.findall(_uncommented(ln))}
        if ups & want:
            out.append(("pure" if ups <= want else "mixed", addrs, a, b))
    return out


def drop(text: str, sites: list[str]) -> str:
    found = find(text, sites)
    gone = {n for _, a, b in found for n in range(a, b + 1)}
    lines = [ln for n, ln in enumerate(text.splitlines()) if n not in gone]
    out, blank = [], False                                    # squeeze the blank lines left behind
    for ln in lines:
        if ln.strip() == "" and blank:
            continue
        blank = ln.strip() == ""
        out.append(ln)
    while out and out[-1].strip() == "":
        out.pop()
    return "\n".join(out) + "\n"


def main(argv: list[str]) -> int:
    if len(argv) < 3 or argv[0] not in ("list", "drop", "ports") or (argv[0] == "drop" and len(argv) < 4):
        print(__doc__.split("\n\n")[1], file=sys.stderr)
        return 2
    cmd, path = argv[0], argv[1]
    if cmd == "ports":
        if not all(p.isdigit() for p in argv[2:]):
            print("caddy_sites: ports must be numbers", file=sys.stderr)
            return 2
        try:
            found = by_ports(open(path).read(), argv[2:])
        except ValueError as e:
            print(f"caddy_sites: {path}: {e}", file=sys.stderr)
            return 2
        for kind, addrs, a, b in found:
            print(f"{kind}\t{addrs[0] if addrs else '-'}\t{' '.join(addrs)}\tlines {a + 1}-{b + 1}")
        return 0
    out_path = argv[2] if cmd == "drop" else None
    sites = argv[3:] if cmd == "drop" else argv[2:]
    text = open(path).read()
    try:
        found = find(text, sites)
    except ValueError as e:
        print(f"caddy_sites: {path}: {e}", file=sys.stderr)
        return 2
    for s, a, b in found:
        print(f"{s}: lines {a + 1}-{b + 1}")
    missing = [s for s in sites if s not in {f[0] for f in found}]
    for s in missing:
        print(f"{s}: not found")
    if cmd == "drop":
        with open(out_path, "w") as f:
            f.write(drop(text, sites))
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
