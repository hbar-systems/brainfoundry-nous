"""cc_recent (scripts/cc/cc_recent.py): the RECENT block over a temp world. Pure functions, no network.

Run from repo root:
    pytest tests/test_cc_recent.py -v
"""
from __future__ import annotations

import importlib.util
import json
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("cc_recent", ROOT / "scripts" / "cc" / "cc_recent.py")
R = importlib.util.module_from_spec(spec); sys.modules["cc_recent"] = R; spec.loader.exec_module(R)


def _stamp(ago_s: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - ago_s))


def _world(tmp_path):
    """A world with every source present: two thread maps (the newer wins), a register, the
    steward queue, three threads (one too old, one archived), two transcripts, the memo tape."""
    ops = tmp_path / "world" / "ops"; (ops / "steward").mkdir(parents=True)
    (ops / "2026-10-11_central-thread-map.md").write_text("# old\n\n## Owed by hbar\n\n1. stale item\n")
    (ops / "2026-10-12_central-thread-map.md").write_text(
        "# Central thread map\n\n## Owed by hbar (read this first)\n\nIntro line.\n\n" +
        "\n".join(f"{i}. owed item {i}" for i in range(1, 16)) + "\n\n## Running now\n\nNothing.\n")
    (ops / "2026-10-12_idea-register.md").write_text(
        "# Idea register\n\n## 2. Themes\n\n- theme\n\n## 3. Owed by hbar, consolidated\n\n" +
        "\n".join(f"{i}. owed {i}" for i in range(1, 13)) +
        "\n\n## 4. Agent queue, in order\n\n1. memo dispatch\n2. modules document\n\n## 5. Where to continue\n\nhere\n\n"
        "## 2026-10-12, later: moved\n\n- hackathon closed\n\n## 2026-10-12, later: what came back\n\n- modules doc\n- ledger merged\n")
    (ops / "steward" / "queue.md").write_text(
        "# Steward queue\n\n## Ready to push, your word\n\n"
        "### world (main): 108 commit(s) ahead; leak check: REFUSED: 2 private-pattern line(s)\nPushing deploys: x\n- 59314ee ops\n\n"
        "### systems/brainfoundry/repos/brainfoundry-nous (main): 1 commit(s) ahead, 5 behind; leak check: clean\n- 56cb6b6 cc\n\n"
        "## Contested (not committed; fix or wait, retried next run)\n\n### systems/x/repos/y: 1 commit(s) ahead; leak check: clean\n\n"
        "## Stale uncommitted\n\n- M ui/pages/cc.js\n")
    state = tmp_path / "state"; state.mkdir()
    (state / "threads.json").write_text(json.dumps([
        {"claude": "aaa", "brain": "b1", "title": "CC: music set", "started": _stamp(7200), "last": _stamp(3600)},
        {"claude": "bbb", "brain": "b2", "title": "CC: science", "started": _stamp(600), "last": _stamp(60)},
        {"claude": "ccc", "brain": "b3", "title": "CC: ancient", "started": _stamp(400000), "last": _stamp(300000)},
        {"claude": "ddd", "brain": "b4", "title": "CC: archived", "started": _stamp(10), "last": _stamp(5), "archived": True},
        {"claude": None, "brain": "b5", "title": "CC: never answered", "started": _stamp(30), "last": _stamp(30)},
    ]))
    projects = tmp_path / "projects"; projects.mkdir()
    (projects / "aaa.jsonl").write_text("\n".join([
        json.dumps({"type": "user", "message": {"role": "user", "content": "hi"}}),
        json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "First answer."}]}}),
        json.dumps({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Read"}]}}),
        json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "  Chapter 3 is  open in Live;\nnothing running. " + "x" * 300}]}}),
        json.dumps({"type": "queue-operation", "operation": "dequeue"}),
        "not json at all",
    ]) + "\n")
    inbox = tmp_path / "in"; memos = inbox / "memos"; (memos / "m1").mkdir(parents=True); (memos / "m2").mkdir()
    (memos / "index.json").write_text(json.dumps({"memos_dir": str(memos), "memos": [
        {"id": "m1", "stage": "filed", "review_done": True, "n_pending": 0},
        {"id": "m2", "stage": "ruled", "review_done": False, "n_pending": 7},
    ]}))
    (memos / "m1" / "bits.json").write_text(json.dumps([
        {"n": 1, "dispatch": {"state": "sent", "id": "J1"}}, {"n": 2, "dispatch": {"state": "held", "reason": "someday"}}, {"n": 3}]))
    (memos / "m2" / "bits.json").write_text(json.dumps({"bits": [{"n": 1, "dispatch": {"state": "held"}}]}))
    return tmp_path / "world", state, projects, inbox


def test_block_has_every_part_in_order_with_its_source(tmp_path):
    R._CACHE.clear()
    world, state, projects, inbox = _world(tmp_path)
    b = R.recent_block(world, state, projects_dir=projects, in_dir=inbox)
    heads = ["## Owed by hbar (ops/2026-10-12_central-thread-map.md)", "## Idea register (ops/2026-10-12_idea-register.md)",
             "## Ready to push (ops/steward/queue.md)", "## Threads active in the last 48 h (", "## Memo tape ("]
    pos = [b.index(h) for h in heads]
    assert pos == sorted(pos)
    # 1. the newest map, 12 lines of the section, not the heading's siblings
    assert "stale item" not in b and "Intro line." in b and "11. owed item 11" in b and "12. owed item 12" not in b and "Nothing." not in b
    # 2. the register: 10 lines of section 3, section 4, the last dated section
    assert "10. owed 10" in b and "11. owed 11" not in b and "2. modules document" in b and "here" not in b.split("### 2026-10-12, later: what came back")[0].split("### 4. Agent queue")[1]
    assert "### 2026-10-12, later: what came back\n- modules doc\n- ledger merged" in b and "hackathon closed" not in b
    # 3. the ready-to-push repos only, one line each
    assert "- world: 108 ahead; leak check: REFUSED: 2 private-pattern line(s)" in b
    assert "- systems/brainfoundry/repos/brainfoundry-nous: 1 ahead, 5 behind; leak check: clean" in b
    assert "systems/x/repos/y" not in b and "ui/pages/cc.js" not in b and "59314ee" not in b
    # 4. threads: newest first, old and archived out, last brain sentence clipped and flattened
    t = b.split("## Threads active")[1].split("## Memo tape")[0]
    assert t.index("CC: never answered") < t.index("CC: science") < t.index("CC: music set")
    assert "CC: ancient" not in t and "CC: archived" not in t
    assert "(no transcript)" in t   # bbb.jsonl is missing, b5 has no claude id
    said = [ln for ln in t.splitlines() if "CC: music set" in ln][0].split("): ", 1)[1]
    assert said.startswith("Chapter 3 is open in Live; nothing running. x") and len(said) == 160
    # 5. the memo tape in one line
    assert "2 memos, 1 pending signoff, 7 bits pending, dispatch held 2 / sent 1" in b


def test_missing_sources_say_none_and_nothing_raises(tmp_path):
    R._CACHE.clear()
    b = R.recent_block(tmp_path / "nowhere", tmp_path / "nostate", projects_dir=tmp_path / "p", in_dir=tmp_path / "i")
    assert b.count("(none)") == 5
    for h in ("## Owed by hbar (no ops/*_central-thread-map.md)", "## Idea register (no ops/*_idea-register.md)",
              "## Ready to push (no ops/steward/queue.md)", "## Threads active in the last 48 h (", "## Memo tape ("):
        assert h in b
    (tmp_path / "nostate").mkdir(); (tmp_path / "nostate" / "threads.json").write_text("{not json")
    R._CACHE.clear()
    assert "(none)" in R.recent_block(tmp_path / "nowhere", tmp_path / "nostate", projects_dir=tmp_path / "p", in_dir=tmp_path / "i")


def test_cap_and_cache(tmp_path):
    R._CACHE.clear()
    world, state, projects, inbox = _world(tmp_path)
    small = R.recent_block(world, state, max_chars=800, projects_dir=projects, in_dir=inbox)
    assert len(small) <= 800 and "(cut)" in small
    assert "dispatch held 2 / sent 1" in small   # the short parts keep their lines; the long ones are trimmed
    assert sum(1 for ln in small.splitlines() if ln.startswith("## ")) == 5
    R._CACHE.clear()
    (world / "ops" / "2026-10-13_central-thread-map.md").write_text("# m\n\n## Owed by hbar\n\n1. " + "long " * 100 + "\n")
    assert "long long ..." in R.recent_block(world, state, projects_dir=projects, in_dir=inbox)   # an ops line clipped to its gist
    first = R.recent_block(world, state, projects_dir=projects, in_dir=inbox)
    (world / "ops" / "2026-10-13_central-thread-map.md").write_text("# newer\n\n## Owed by hbar\n\n1. brand new\n")
    assert R.recent_block(world, state, projects_dir=projects, in_dir=inbox) == first   # cached for 120 s
    R._CACHE.clear()
    assert "brand new" in R.recent_block(world, state, projects_dir=projects, in_dir=inbox)


def test_project_slug_matches_the_reasoners_folder():
    assert R.project_slug("/home/hands/world") == "-home-hands-world"
    assert R.project_slug("/home/hbar/brain") == "-home-hbar-brain"
