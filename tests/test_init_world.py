"""The world template (templates/world) and scripts/cc/init-world.sh: the exact tree lands,
one first commit, placeholders fill from the interview's JSON export, a second run never
overwrites. Needs git and python3 on PATH; no reasoner, no network.

Run from repo root:
    pytest tests/test_init_world.py -v
"""
from __future__ import annotations

import json
import pathlib
import re
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "cc" / "init-world.sh"
TEMPLATE = ROOT / "templates" / "world"

# the eleven required items of ops/2026-10-12_brain-template-folder.md
REQUIRED = ["CLAUDE.md", "ME.md", "NOW.md", "DEVICES.md", "APPS.md", "decisions.md", "ideas.md",
            "areas/README.md", "library/MANIFEST.md", "journal/TEMPLATE.md", ".gitignore"]

ANSWERS = {
    "version": 5, "person": "Mara", "date": "2026-10-10", "interviewer": "the observer",
    "consentRecord": "yes", "consentScience": "no",
    "answers": {
        "A4": "that I teach music\nand which instruments", "A7": "lesson plans",
        "A8_read": "allowed", "A8_write": "ask", "A8_send": "never", "A8_cal_see": "allowed", "A8_cal_change": "ask",
        "A8_web": "allowed", "A8_remember": "allowed", "A8_spend": "never", "A8_post": "never", "A8_else": "book rooms",
        "A9": "my students' names", "A10_work": "a music teacher", "A10_lang": "Slovak",
        "A11": "keep my lesson notes in one place", "A12": "I stop re-typing plans", "A13": "if it loses a note",
        "B1": "a teacher", "B2": "the lessons folder, 2 GB, PDFs and audio", "B7": "calendar and email, not messages",
        "B9": "light", "B10_1": "calm", "B10_3": "any", "B11": "a quiet practice room",
        "B12_length": "short", "B12_tone": "casual", "B12_lang": "Slovak and English", "B12_humour": "yes", "B12_size": "large",
        "B17": "the school's grading system", "B17_first": "the lesson planner",
        "B21_on": "yes", "B21_net": "yes", "B21_candidate": "the old desktop",
    },
    "devices": [
        {"kind": "laptop", "model": "Air M2", "system": "macOS", "age": "2 years", "whose": "theirs", "use": "daily", "local": "yes", "join": "joins"},
        {"kind": "", "model": "", "system": "", "age": "", "whose": "", "use": "", "local": "", "join": ""},
    ],
    "oldDevices": [{"kind": "desktop", "model": "old tower", "system": "Windows", "age": "8 years", "whose": "theirs", "use": "rarely", "local": "no", "join": "ask"}],
    "storage": [{"name": "iCloud", "size": "50-500 GB", "join": "outside"}],
    "notes": {"A": "", "B": "", "C": "", "D": ""}, "custom": [],
}


def run(*args, check=True):
    return subprocess.run(["bash", str(SCRIPT), *args], capture_output=True, text=True, check=check)


def git(world, *args):
    return subprocess.run(["git", "-C", str(world), *args], capture_output=True, text=True, check=True).stdout.strip()


def test_template_ships_the_required_items_with_dates_and_no_private_names():
    for rel in REQUIRED:
        assert (TEMPLATE / rel).is_file(), rel
    shipped = sorted(str(p.relative_to(TEMPLATE)) for p in TEMPLATE.rglob("*") if p.is_file())
    assert shipped == sorted(REQUIRED), "nothing else ships (the note: eleven required items)"
    for rel in REQUIRED:
        text = (TEMPLATE / rel).read_text()
        assert "Created: " in text, f"{rel} has no creation-date line"
        low = text.lower()
        for word in ("hbar", "yury", "anne", "synthesis.md", "focus.md", "ops/", "systems/"):
            # whole words only: "planned" is not "anne" (2026-10-12)
            assert not re.search(r"(?<![a-z0-9])" + re.escape(word) + r"(?![a-z0-9])", low), \
                f"{rel} carries a private or hbar-specific name: {word}"


def test_first_run_lands_the_tree_and_one_commit(tmp_path):
    world = tmp_path / "world"
    persona = tmp_path / "persona.md"
    answers = tmp_path / "a.json"
    answers.write_text(json.dumps(ANSWERS))
    r = run("--target", str(world), "--answers", str(answers), "--persona-out", str(persona), "--date", "2026-10-12")
    for rel in REQUIRED:
        assert (world / rel).is_file(), rel
    # the areas from the interview: B1 "a teacher" -> study; mail in B7 -> inbox
    assert (world / "areas" / "study" / "README.md").is_file()
    assert (world / "areas" / "study" / "notes").is_dir()
    assert (world / "areas" / "inbox" / "README.md").is_file()
    # one commit, the person's identity, a clean tree, main branch
    assert git(world, "rev-list", "--count", "HEAD") == "1"
    assert git(world, "log", "-1", "--format=%s") == "world: opened 2026-10-12"
    assert git(world, "log", "-1", "--format=%an") == "Mara"
    assert git(world, "status", "--porcelain") == ""
    assert git(world, "rev-parse", "--abbrev-ref", "HEAD") == "main"
    assert git(world, "ls-files", ".gitignore") == ".gitignore"
    # the D1 line is printed for the operator
    assert "D1 (2026-10-12): brain opened 2026-10-12, interview v5, first area study." in r.stdout
    # persona seeded once from ME.md's one line
    assert persona.is_file() and "Mara is a music teacher, Slovak and English speaker." in persona.read_text()


def test_placeholders_fill_from_the_interview_export(tmp_path):
    world = tmp_path / "world"
    answers = tmp_path / "a.json"
    answers.write_text(json.dumps(ANSWERS))
    run("--target", str(world), "--answers", str(answers), "--date", "2026-10-12")
    texts = {rel: (world / rel).read_text() for rel in REQUIRED}
    for rel, text in texts.items():
        assert "{{" not in text, f"{rel} still has a placeholder token"
    claude = texts["CLAUDE.md"]
    assert "| Read my messages | allowed |" in claude
    assert "| Write messages for me | ask me first |" in claude
    assert "| Send messages for me | never |" in claude
    assert "| Anything else | book rooms |" in claude
    assert "Never tell: my students' names" in claude
    assert "Stays outside: the school's grading system" in claude
    me = texts["ME.md"]
    assert "- Name: Mara" in me and "- Language(s): Slovak and English" in me
    assert "that I teach music; and which instruments" in me      # multi-line answers become one line
    assert "calm, -, don't care, -, -, -" in me                    # B10 pairs in order, any -> don't care
    now = texts["NOW.md"]
    assert "In the first week it should: keep my lesson notes in one place" in now
    assert "I would stop using it if: if it loses a note" in now
    assert "First area: areas/study/" in now
    dev = texts["DEVICES.md"]
    assert "| laptop Air M2 | macOS | theirs | daily | yes | (fill in) | compute |" in dev
    assert "| desktop old tower (not in use) | Windows | theirs | no longer | ask me first | (fill in) | store |" in dev
    assert "| iCloud (storage, 50-500 GB) | | | | no | files | source |" in dev
    assert "Always-on machine at home: the old desktop. Home internet steady: yes." in dev
    assert "Apps to connect (B7): calendar and email, not messages" in texts["APPS.md"]
    assert "Planned first import (from the interview, B2): the lessons folder, 2 GB, PDFs and audio" in texts["library/MANIFEST.md"]
    area = (world / "areas" / "study" / "README.md").read_text()
    assert "the lessons folder, 2 GB, PDFs and audio" in area and "the school's grading system" in area


def test_without_answers_every_placeholder_reads_fill_in(tmp_path):
    world = tmp_path / "world"
    run("--target", str(world), "--date", "2026-10-12")
    for rel in REQUIRED:
        assert "{{" not in (world / rel).read_text(), rel
    assert "| Read my messages | (fill in) |" in (world / "CLAUDE.md").read_text()
    assert (world / "areas" / "general" / "README.md").is_file()
    assert "Created: 2026-10-12" in (world / "ME.md").read_text()
    assert git(world, "rev-list", "--count", "HEAD") == "1"


def test_second_run_never_overwrites(tmp_path):
    world = tmp_path / "world"
    answers = tmp_path / "a.json"
    answers.write_text(json.dumps(ANSWERS))
    run("--target", str(world), "--answers", str(answers), "--date", "2026-10-12")
    (world / "NOW.md").write_text("# NOW\n\nthe person's own state\n")
    head = git(world, "rev-parse", "HEAD")
    r = run("--target", str(world), "--answers", str(answers), "--date", "2026-10-13")
    assert "already open" in r.stdout and "nothing done" in r.stdout
    assert (world / "NOW.md").read_text() == "# NOW\n\nthe person's own state\n"
    assert git(world, "rev-parse", "HEAD") == head
    assert git(world, "rev-list", "--count", "HEAD") == "1"
    # a persona file that exists is left as it is too
    persona = tmp_path / "persona.md"
    persona.write_text("mine\n")
    run("--target", str(world), "--persona-out", str(persona))
    assert persona.read_text() == "mine\n"


def test_refuses_a_non_world_folder_with_content(tmp_path):
    target = tmp_path / "notes"
    target.mkdir()
    (target / "keep.txt").write_text("x")
    r = run("--target", str(target), check=False)
    assert r.returncode == 2 and "refusing" in r.stdout
    assert (target / "keep.txt").read_text() == "x" and not (target / "CLAUDE.md").exists()
