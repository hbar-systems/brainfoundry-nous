"""tests/test_cc_listen.py: the bridge side of /listen (scripts/cc/cc_listen.py, LISTEN-1 2026-11-24)."""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "cc"))
import cc_listen  # noqa: E402


def tsv(p: Path, header, rows):
    with open(p, "w", newline="") as f:
        w = csv.writer(f, delimiter="\t", lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)


VID = lambda c: (c * 11)[:11]  # noqa: E731


@pytest.fixture
def world(tmp_path):
    d = tmp_path / "world" / "systems" / "x.music" / "ops" / "listening"
    d.mkdir(parents=True)
    tsv(d / "2026-11-20_playlists-all.tsv", ["account", "playlist_id", "title", "created"], [["a", "PLold", "old list", "2026-01-01"]])
    tsv(d / "2026-11-23_playlists-all.tsv", ["account", "playlist_id", "title", "created"], [
        ["a", "PLb2", "beats II", "2026-08-25"], ["a", "PLb1", "Beats", "2026-07-15"], ["a", "PLh", "house 1", "2026-10-13"],
        ["a", "PLempty", "empty", "2026-11-01"]])
    tsv(d / "2026-11-23_playlist-items.tsv", ["playlist_id", "video_id", "title", "artist_guess", "duration_s"], [
        ["PLb2", VID("a"), "A", "Art A", "150"], ["PLb2", VID("a"), "A again", "Art A", "150"], ["PLb2", "bad id", "x", "", ""],
        ["PLb2", VID("c"), "C", "Art C", "x"], ["PLb1", VID("d"), "D", "", ""], ["PLh", VID("e"), "E", "Art E", "300"]])
    tsv(d / "2026-11-23_listening.tsv", ["video_id", "title", "channel", "artist_guess", "music", "styles", "liked"], [
        [VID("a"), "A", "c", "Art A", "yes", "beat (rap instrumental)", "no"],
        [VID("e"), "E", "c", "Art E", "yes", "house, deep house", "yes"],
        [VID("g"), "G house", "c", "Art G", "yes", "", "no"],
        [VID("n"), "talk", "c", "", "no", "house", "no"]])
    (d / "2026-11-23_taste.md").write_text("## Genres, most first\n\n1. House: afro house, deep house. The biggest share of playlists.\n"
                                           "2. Rap beats: boom bap (399 videos).\n\n## Artists\n\n1. Not a genre: ignored.\n")
    (d / "listen.json").write_text(json.dumps({"first": ["beats"]}))
    (tmp_path / "world" / "m").mkdir()
    (tmp_path / "world" / "m" / "t.mp3").write_bytes(b"ID3" + b"\0" * 2000)
    (tmp_path / "secret.mp3").write_bytes(b"no")
    tsv(d / "own.tsv", ["id", "title", "artist", "file", "duration_s"], [
        ["t", "Mine", "me", "m/t.mp3", "100"], ["out", "Outside", "me", "../../secret.mp3", ""],
        ["Bad Id", "x", "me", "m/t.mp3", ""], ["missing", "x", "me", "m/none.mp3", ""]])
    return tmp_path


def L(world):
    return cc_listen.Listen(str(world / "world"), world / "state", world / "out" / "listen" / "plays.tsv")


def test_station_order_and_items(world):
    s = L(world).state()
    assert [x["id"] for x in s["stations"]] == ["pl:PLb2", "pl:PLb1", "likes", "own", "mix", "pl:PLh"]
    assert s["stations"][0]["first"] is True and "first" not in s["stations"][-1]
    code, d = L(world).station("pl:PLb2")
    assert code == 200
    assert [i["id"] for i in d["items"]] == [VID("a"), VID("c")]          # deduped, the bad id dropped
    assert d["items"][0] == {"k": "yt", "id": VID("a"), "title": "A", "artist": "Art A", "dur": 150}
    assert "dur" not in d["items"][1]


def test_likes_from_records_when_no_likes_table(world):
    code, out = L(world).station("likes")                                 # no likes table: the records' liked=yes
    assert code == 200 and [i["id"] for i in out["items"]] == [VID("e")]
    d = world / "world" / "systems" / "x.music" / "ops" / "listening"
    tsv(d / "2026-11-23_youtube-likes.tsv", ["source", "video_id", "title", "artist_guess"], [["LL", VID("f"), "F", "Art F"]])
    s2 = L(world)
    code, out = s2.station("likes")
    assert code == 200 and [i["id"] for i in out["items"]] == [VID("f")]


def test_taste_genres_and_mix(world):
    g = cc_listen.taste_genres((world / "world/systems/x.music/ops/listening/2026-11-23_taste.md").read_text())
    assert [x["name"] for x in g] == ["House", "Rap beats"]
    assert "biggest" not in g[0]["words"] and "playlist" not in g[0]["words"]
    code, d = L(world).station("mix")
    ids = [i["id"] for i in d["items"]]
    assert VID("n") not in ids                                             # not music
    assert ids[0] == VID("e")                                              # the liked house item leads the first genre
    assert set(ids) == {VID("e"), VID("g"), VID("a")}
    assert cc_listen.mix([], g, "2026-11-24") == []


def test_own_files_only_listed_inside_world(world):
    s = L(world)
    assert s.file_for("t").name == "t.mp3"
    for n in ("out", "Bad Id", "missing", "../t", "", None, "t/../t"):
        assert s.file_for(n) is None
    code, d = s.station("own")
    assert [i["n"] for i in d["items"]] == ["t"]


def test_station_id_checked(world):
    s = L(world)
    for bad in ("", None, "pl:", "pl:../x", "likes;", 5):
        assert s.station(bad)[0] == 400
    assert s.station("pl:PLnope")[0] == 404


def test_event_log(world):
    s = L(world)
    ok = {"event": "start", "station": "pl:PLb2", "kind": "yt", "item": VID("a"), "title": "A\tB", "artist": "Art",
          "position_s": 0, "duration_s": 150, "tz": "Europe/Bratislava", "tab": "hidden"}
    assert s.event(ok) == (200, {"ok": True})
    assert s.event({**ok, "event": "finish", "position_s": 149.96})[0] == 200
    assert s.event({**ok, "kind": "file", "item": "t", "station": "own", "event": "blocked", "reason": "file", "tz": "bad tz!"})[0] == 200
    for bad in ({**ok, "event": "delete"}, {**ok, "station": "x"}, {**ok, "kind": "mp3"}, {**ok, "item": "short"},
                {**ok, "kind": "file", "item": "../x"}, {**ok, "station": "pl:PLnope"}, "nope"):
        assert s.event(bad)[0] in (400, 404)
    with open(world / "out" / "listen" / "plays.tsv", newline="") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))
    assert list(rows[0].keys()) == list(cc_listen.LOG_COLUMNS)
    assert [r["event"] for r in rows] == ["start", "finish", "blocked"]
    assert rows[0]["title"] == "A B" and rows[0]["station"] == "beats II" and rows[0]["browser_tz"] == "Europe/Bratislava"
    assert rows[1]["position_s"] == "150.0" and rows[2]["browser_tz"] == ""
    assert rows[0]["tab"] == "hidden"
    assert s.event({**ok, "tab": "minimised"})[0] == 200
    with open(world / "out" / "listen" / "plays.tsv", newline="") as f:
        assert list(csv.DictReader(f, delimiter="\t"))[-1]["tab"] == ""
    assert rows[0]["ts_utc"].endswith("Z") and len(rows[0]["ts_utc"]) == 20


def test_event_day_cap(world, monkeypatch):
    monkeypatch.setattr(cc_listen, "MAX_ROWS_DAY", 2)
    s = L(world)
    ok = {"event": "start", "station": "own", "kind": "file", "item": "t"}
    assert s.event(ok)[0] == 200 and s.event(ok)[0] == 200
    assert s.event(ok)[0] == 429
    assert L(world).event(ok)[0] == 429                                    # a restarted bridge counts the file


def test_no_world_says_why(tmp_path):
    s = cc_listen.Listen(None, tmp_path, tmp_path / "p.tsv").state()
    assert s["stations"] == [] and "listening" in s["why"]


def test_member_read_is_used_when_world_has_none(tmp_path):
    (tmp_path / "state" / "listening").mkdir(parents=True)
    tsv(tmp_path / "state" / "listening" / "listening.tsv", ["video_id", "title", "artist_guess", "music", "styles", "liked"],
        [[VID("q"), "Q", "Art", "yes", "house", "yes"]])
    s = cc_listen.Listen(None, tmp_path / "state", tmp_path / "p.tsv")
    code, d = s.station("likes")
    assert code == 200 and d["items"][0]["id"] == VID("q")
