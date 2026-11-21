"""Every file the api Dockerfile COPYs from the repo root must survive .dockerignore.

Created 2026-11-21 (MEMBERS-7): twice a new COPY of a file under scripts/ broke every member
Update at build time (f7a4093 on 2026-11-03, SPOKE-3 on 2026-11-16) because .dockerignore drops
scripts/ and only re-includes listed files. This reads the api build context the way the builder
does for these simple patterns: last matching line wins, '!' re-includes.
"""
import fnmatch
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _patterns():
    out = []
    for line in (ROOT / ".dockerignore").read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        neg = line.startswith("!")
        out.append((neg, line[1:] if neg else line))
    return out


def _ignored(path, patterns):
    parts = path.split("/")
    ignored = False
    for neg, pat in patterns:
        pat = pat.strip("/")
        hit = any(fnmatch.fnmatch("/".join(parts[: i + 1]), pat) for i in range(len(parts)))
        if hit:
            ignored = not neg
    return ignored


def _copy_sources():
    srcs = []
    for line in (ROOT / "api" / "Dockerfile").read_text().splitlines():
        m = re.match(r"\s*COPY\s+(?!--from)(.+)", line)
        if not m:
            continue
        args = [a for a in m.group(1).split() if not a.startswith("--")]
        srcs += [a.lstrip("./") for a in args[:-1]]
    return srcs


def test_api_copy_sources_are_in_the_build_context():
    pats = _patterns()
    srcs = _copy_sources()
    assert srcs, "no COPY lines read from api/Dockerfile"
    dropped = [s for s in srcs if s and s != "." and _ignored(s, pats)]
    assert not dropped, "api/Dockerfile COPYs files .dockerignore drops: %s" % dropped


def test_copied_files_exist():
    for s in _copy_sources():
        if s and s != "." and "*" not in s:
            assert (ROOT / s).exists(), s
