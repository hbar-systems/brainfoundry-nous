"""The orfeo library search on /take (DEMO-2, 2026-11-25): scripts/cc/cc_find.py, with YouTube stubbed.

The owner asked that what goes under the voice comes from their own YouTube music by search, not only from saved
playlists. These tests hold the bridge to its word: the library in the brain answers first (own tracks, likes, then
the first playlists, then the others; every word must match; accents and case do not matter); typing never reaches
YouTube; the live search runs only on the press, through GET actions only, is cached a day and capped per day; a
result whose embedding is off (or that is gone) comes back greyed with its reason; recent tracks and shortcuts come
with an empty query; a pick's flag can be checked alone."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "cc"))
import cc_find  # noqa: E402

PAGE = (ROOT / "ui" / "pages" / "take.js").read_text()


class FakeListen:
    def _load(self):
        return {"stations": [
            {"id": "pl:B11", "name": "BEATS XI", "kind": "playlist", "first": True, "items": [
                {"k": "yt", "id": "AAAAAAAAAA1", "title": "[FREE] Eminem Type Beat - EXECUTE", "artist": "Jack Parker Beats", "dur": 200},
                {"k": "yt", "id": "AAAAAAAAAA2", "title": "Dark Trap Beat", "artist": "Somebody"}]},
            {"id": "likes", "name": "my likes", "kind": "likes", "items": [
                {"k": "yt", "id": "AAAAAAAAAA3", "title": "Halo", "artist": "Beyoncé"},
                {"k": "yt", "id": "AAAAAAAAAA1", "title": "[FREE] Eminem Type Beat - EXECUTE", "artist": "Jack Parker Beats"}]},
            {"id": "own", "name": "my own tracks", "kind": "own", "items": [
                {"k": "file", "n": "industry", "title": "INDUSTRY", "artist": "hbar"}]},
            {"id": "pl:OLD", "name": "old stuff", "kind": "playlist", "items": [
                {"k": "yt", "id": "AAAAAAAAAA4", "title": "Industry Baby", "artist": "Lil Nas X"}]},
        ]}


class FakeTake:
    def __init__(self, takes=None):
        self.takes = takes or []

    def state(self):
        return {"takes": self.takes}


class FakeYT:
    """Stands in for one-read: answers search.list and videos.list, records every call."""
    def __init__(self, blocked=(), gone=(), fail=False, region=None):
        self.calls, self.blocked, self.gone, self.fail, self.region = [], set(blocked), set(gone), fail, region or {}

    def __call__(self, action, key, q):
        self.calls.append((action, key, dict(q)))
        if self.fail:
            raise RuntimeError("YouTube refused: quotaExceeded")
        if action == cc_find.SEARCH_ACTION:
            return {"items": [
                {"id": {"kind": "youtube#video", "videoId": "BBBBBBBBBB1"}, "snippet": {"title": "Lose Yourself (Instrumental) &amp; more", "channelTitle": "Eminem"}},
                {"id": {"kind": "youtube#video", "videoId": "BBBBBBBBBB2"}, "snippet": {"title": "Blocked one", "channelTitle": "Label"}},
                {"id": {"kind": "youtube#channel", "channelId": "UCx"}, "snippet": {"title": "a channel"}}]}
        if action == cc_find.VIDEOS_ACTION:
            ids = [i for i in q["id"].split(",") if i not in self.gone]
            if q["part"] == "status":
                return {"items": [{"id": i, "status": {"embeddable": i not in self.blocked, "privacyStatus": "public",
                                                       "uploadStatus": "processed"}} for i in ids]}
            return {"items": [{"id": i, "contentDetails": {"duration": "PT3M26S", **({"regionRestriction": self.region[i]} if i in self.region else {})}} for i in ids]}
        raise AssertionError(action)


def make(tmp_path, yt=None, takes=None, per_day=60, clock=None):
    yt = yt or FakeYT()
    f = cc_find.Find(FakeListen(), FakeTake(takes), tmp_path, get=yt, per_day=per_day, clock=clock or (lambda: 1_800_000_000.0))
    return f, yt


def test_library_first_own_then_likes_then_first_playlists_and_every_word(tmp_path):
    f, yt = make(tmp_path)
    _, d = f.find("industry")
    assert [i.get("n") or i["id"] for i in d["library"]] == ["industry", "AAAAAAAAAA4"]
    assert d["library"][0]["src"] == "my own tracks" and d["library"][0]["embed"] is True
    _, d = f.find("eminem execute")
    assert [i["id"] for i in d["library"]] == ["AAAAAAAAAA1"] and d["library"][0]["src"] == "my likes"
    _, d = f.find("BEYONCE halo")                       # accents and case do not matter
    assert [i["id"] for i in d["library"]] == ["AAAAAAAAAA3"]
    _, d = f.find("beats xi trap")                       # the playlist's name counts as words too
    assert [i["id"] for i in d["library"]] == ["AAAAAAAAAA2"]
    assert d["live"] is None
    assert yt.calls == []                                # typing never reaches YouTube


def test_live_search_on_press_get_only_unescaped_and_flags(tmp_path):
    f, yt = make(tmp_path, FakeYT(blocked={"BBBBBBBBBB2"}))
    _, d = f.find("lose yourself", live=True)
    items = d["live"]["items"]
    assert [i["id"] for i in items] == ["BBBBBBBBBB1", "BBBBBBBBBB2"]   # the channel result is not a track
    assert items[0]["title"] == "Lose Yourself (Instrumental) & more" and items[0]["artist"] == "Eminem"
    assert items[0]["embed"] is True and items[0]["dur"] == 206
    assert items[1]["embed"] is False and "embedding is off" in items[1]["why"]
    assert {c[0] for c in yt.calls} <= {cc_find.SEARCH_ACTION, cc_find.VIDEOS_ACTION}   # list actions only (GET)
    assert d["live_left"] == 59


def test_gone_video_is_greyed_with_its_reason(tmp_path):
    f, yt = make(tmp_path, FakeYT(gone={"BBBBBBBBBB1"}))
    _, d = f.find("lose yourself", live=True)
    gone = d["live"]["items"][0]
    assert gone["embed"] is False and gone["why"] == cc_find.WHY_GONE


def test_live_cached_a_day_and_flags_a_week(tmp_path):
    t = [1_800_000_000.0]
    f, yt = make(tmp_path, clock=lambda: t[0])
    f.find("lose yourself", live=True)
    n = len(yt.calls)
    _, d = f.find("Lose   YOURSELF", live=True)
    assert d["live"]["cached"] is True and len(yt.calls) == n and d["live_left"] == 59
    f2, yt2 = make(tmp_path, clock=lambda: t[0])          # the cache is on disk: a restart keeps it
    _, d = f2.find("lose yourself", live=True)
    assert d["live"]["cached"] and yt2.calls == []
    t[0] += 25 * 3600
    f3, yt3 = make(tmp_path, clock=lambda: t[0])
    f3.find("lose yourself", live=True)
    assert [c[0] for c in yt3.calls] == [cc_find.SEARCH_ACTION]   # searched again; flags still fresh (a week)


def test_daily_cap_stops_live_but_library_answers(tmp_path):
    f, yt = make(tmp_path, per_day=1)
    f.find("one", live=True)
    _, d = f.find("eminem", live=True)
    assert d["live"]["ok"] is False and "searches are used" in d["live"]["why"]
    assert d["library"] and d["live_left"] == 0


def test_youtube_refusal_is_said_not_raised(tmp_path):
    f, yt = make(tmp_path, FakeYT(fail=True))
    code, d = f.find("anything", live=True)
    assert code == 200 and d["live"]["ok"] is False and "quotaExceeded" in d["live"]["why"]


def test_empty_query_gives_recent_and_shortcuts(tmp_path):
    takes = [{"over": {"kind": "embed", "video_id": "AAAAAAAAAA1", "title": "EXECUTE", "artist": "Jack Parker Beats"}},
             {"over": {"kind": "embed", "video_id": "AAAAAAAAAA1", "title": "EXECUTE"}},
             {"over": {"kind": "own", "n": "industry", "title": "INDUSTRY"}},
             {"over": {"kind": "none"}}]
    f, yt = make(tmp_path, FakeYT(blocked={"AAAAAAAAAA1"}), takes=takes)
    _, d = f.find("")
    assert [i.get("id") or i.get("n") for i in d["recent"]] == ["AAAAAAAAAA1", "industry"]
    assert d["recent"][0]["embed"] is False
    assert [s["name"] for s in d["shortcuts"]] == ["BEATS XI", "my likes"]
    assert d["library"] == [] and d["live"] is None


def test_check_one_pick(tmp_path):
    f, yt = make(tmp_path, FakeYT(blocked={"CCCCCCCCCC1"}))
    code, d = f.check("CCCCCCCCCC1")
    assert code == 200 and d["embed"] is False and d["why"] == cc_find.WHY_OFF
    assert f.check("../etc")[0] == 400


def test_no_one_connection_says_so(tmp_path):
    f = cc_find.Find(FakeListen(), FakeTake(), tmp_path, one_read=str(tmp_path / "nope"))
    _, d = f.find("eminem", live=True)
    assert d["library"] and d["live"]["ok"] is False and "connected" in d["live"]["why"]


def test_module_never_downloads():
    src = (ROOT / "scripts" / "cc" / "cc_find.py").read_text()
    for word in ("yt-dlp", "youtube-dl", "urlretrieve", "ffmpeg"):
        assert word not in src


def test_page_names_orfeo_and_greys_blocked():
    assert "orfeo library" in PAGE
    assert "/cc/take/find" in PAGE
    assert "drop the file instead" in PAGE
    assert "embedding off" in PAGE


def test_region_blocked_almost_everywhere_is_greyed(tmp_path):
    f, yt = make(tmp_path, FakeYT(region={"BBBBBBBBBB1": {"blocked": [f"C{i}" for i in range(249)]},
                                          "BBBBBBBBBB2": {"blocked": ["DE"]}}))
    _, d = f.find("lose yourself", live=True)
    a, b = d["live"]["items"]
    assert a["embed"] is False and a["why"] == "YouTube blocks it in 249 countries"
    assert b["embed"] is True                                   # one country blocked: still plays for most
    assert cc_find.region_why({"allowed": ["JP"]}) == "YouTube plays it in 1 country only"
