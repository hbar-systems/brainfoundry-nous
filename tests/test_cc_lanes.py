"""THREADS-1 (2026-11-18): production lanes and the idle archive of the thread list.

    pytest tests/test_cc_lanes.py -v
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "cc"))
import cc_lanes  # noqa: E402

DAY = 86400.0
NOW = 1_795_000_000.0   # 2026-11-18


def iso(t):
    import time
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))


def test_words_pick_a_lane_and_none_says_nothing():
    assert cc_lanes.lane_of_words("film page: sketch boards and the animatic") == "film"
    assert cc_lanes.lane_of_words("CC: render the stems of the new track") == "music"
    assert cc_lanes.lane_of_words("member brain for paul, onboarding") == "brains"
    assert cc_lanes.lane_of_words("front page favicon on vercel") == "sites"
    assert cc_lanes.lane_of_words("eval of six models, brier scores") == "science"
    assert cc_lanes.lane_of_words("steward queue and the ledger") == "ops"
    assert cc_lanes.lane_of_words("hello there") == ""


def test_registry_and_owner_file_come_before_words(tmp_path):
    (tmp_path / "registry").mkdir()
    (tmp_path / "registry" / "systems.json").write_text(json.dumps({"systems": [
        {"id": "hbar.music", "description": "a website for songs"},
        {"id": "orbit.x", "description": "research lab for experiments"},
        {"id": "plain.thing", "description": "nothing here"}]}))
    lanes = cc_lanes.Lanes(tmp_path)
    assert lanes.of("CC: hbar.music front page") == "music"     # the id's own words beat the description and the title
    assert lanes.of("CC: orbit.x site copy") == "science"        # the description, when the id says nothing
    assert lanes.of("x", system="hbar.music") == "music"         # a standing system thread
    assert lanes.of("CC: plain.thing deploy") == "ops"           # unmapped id: the words
    (tmp_path / "ops" / "threads").mkdir(parents=True)
    (tmp_path / "ops" / "threads" / "lanes.json").write_text(json.dumps(
        {"systems": {"plain.thing": "film"}, "keywords": [["k2", "music"], ["bad", "nope"]]}))
    lanes2 = cc_lanes.Lanes(tmp_path)
    assert lanes2.of("CC: plain.thing deploy") == "film"
    assert lanes2.of("K2 bars, the site") == "music"
    assert lanes2.owner["keywords"] == [("k2", "music")]          # an unknown lane is dropped
    assert cc_lanes.Lanes("").of("the album") == "music"          # no world: words only


def test_idle_sweep_archives_quiet_threads_only():
    items = [
        {"brain": "old", "last": iso(NOW - 4 * DAY)},
        {"brain": "fresh", "last": iso(NOW - 1 * DAY)},
        {"brain": "pinned", "last": iso(NOW - 9 * DAY), "pinned": True},
        {"brain": "busy", "last": iso(NOW - 9 * DAY)},
        {"brain": "kept", "last": iso(NOW - 9 * DAY), "kept_at": iso(NOW - 1 * DAY)},
        {"brain": "nodate"},
    ]
    assert cc_lanes.idle_sweep(items, now=NOW, busy={"busy"}) == 1
    got = {x["brain"]: x.get("archived", False) for x in items}
    assert got == {"old": True, "fresh": False, "pinned": False, "busy": False, "kept": False, "nodate": False}
    assert items[0]["archived_by"] == "idle" and items[0]["archived_at"] == iso(NOW)
    assert cc_lanes.idle_sweep(items, now=NOW, busy={"busy"}) == 0   # once
    assert cc_lanes.idle_sweep([{"brain": "a", "last": iso(NOW - 99 * DAY)}], now=NOW, days=0) == 0


def test_by_hand_and_by_turn():
    th = {"brain": "a", "last": iso(NOW - 9 * DAY)}
    cc_lanes.set_archived(th, True, now=NOW)
    assert th["archived"] and th["archived_by"] == "hand"
    cc_lanes.set_archived(th, False, now=NOW)
    assert th["archived"] is False and th["kept_at"] == iso(NOW) and "archived_by" not in th
    assert cc_lanes.idle_sweep([th], now=NOW + DAY) == 0           # brought back: three days from the press
    assert cc_lanes.idle_sweep([th], now=NOW + 3 * DAY) == 1
    assert cc_lanes.unarchive_on_turn(th) is True and th["archived"] is False
    assert cc_lanes.unarchive_on_turn(th) is False
