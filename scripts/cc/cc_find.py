"""cc_find.py: the orfeo library search on /take, what goes under the voice (DEMO-2, 2026-11-25). The bridge side.

The owner, on /take's record step: "WE HAVE TO GET THE TRACK.. WHICH MEANS YOU REACH INTO YOUTUBE MUSIC (VIA
ORFEO.MUSIC... SO BASICALLY ORFEO.MUSIC IS MY ACCOUNT)." One search box over the owner's own music:

  1. the library already in the brain, searched here for free: the owner's own tracks, likes and playlists
     (cc_listen.Listen's stations, read from the world's listening tables), every word of the query in the title,
     artist or playlist name; own tracks first, then likes, then the "first" playlists, then the others;
  2. then, only on the owner's press, a live search of YouTube through the owner's connected account in One
     (one-read: GET only, search.list), cached a day per query and capped per UTC day so YouTube's daily quota
     (search costs 100 of its 10,000 units) is never spent by typing.

Every YouTube result carries whether its embedding is allowed (videos.list part=status, 1 unit per 50 ids, cached a
week per id; asked on the search press, for recent tracks and for a pick, never while typing): {embed: true | false | null (not known yet)} and, when false, {why}. The page plays a pick through the
official embedded player only; this module never fetches, converts or stores audio from YouTube.

Also answered: recent (the last distinct tracks under the owner's takes) and shortcuts (the "first" playlists and the
likes, opened as lists).

  GET /cc/take/find?check=<video id>      {ok, id, embed, why?, dur?}: asked on a pick whose flag is not known
  GET /cc/take/find?q=<words>&live=0|1  {ok, q, recent:[item], shortcuts:[{id,name,count}], library:[item],
                                         live:{ok, items:[item], cached?, why?} | null, live_left}
  item = {k: "yt", id, title, artist, dur?, src, embed, why?} | {k: "file", n, title, artist, dur?, src, embed: true}

Standard library only; YouTube is reached only through the injected `get` (default: one-read), so a test stubs it.
"""
from __future__ import annotations

import html
import json
import os
import re
import subprocess
import threading
import time
import unicodedata
from pathlib import Path

SEARCH_ACTION = "conn_mod_def::GKKPEPj66co::N_9ZRxVwRNGloCs-rFMqiw"   # youtube-data List Search Resources (GET)
VIDEOS_ACTION = "conn_mod_def::GKKPEyCYjmc::jTY7ENAyQ1uugwAPicQ3gg"   # youtube-data List Videos (GET)
VID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
DUR_RE = re.compile(r"^P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$")
LIBRARY_MAX = 30
LIVE_MAX = 10
RECENT_MAX = 6
LIVE_PER_DAY = 60            # 60 searches = 6,000 of YouTube's 10,000 daily units; the rest stays for listening reads
QUERY_TTL = 24 * 3600
EMBED_TTL = 7 * 24 * 3600
KEYS_TTL = 3600
WHY_OFF = "embedding is off: its uploader does not let it play on other sites"
WHY_GONE = "removed or private on YouTube"
REGION_MANY = 100           # blocked in this many countries or more (or allowed in fewer than 50): greyed as well


def region_why(rr) -> str:
    """contentDetails.regionRestriction -> a reason when the video plays in too few places, else ''."""
    if not isinstance(rr, dict):
        return ""
    blocked, allowed = rr.get("blocked"), rr.get("allowed")
    if isinstance(blocked, list) and len(blocked) >= REGION_MANY:
        return f"YouTube blocks it in {len(blocked)} countries"
    if isinstance(allowed, list) and len(allowed) < 50:
        return f"YouTube plays it in {len(allowed)} {'country' if len(allowed) == 1 else 'countries'} only"
    return ""


def norm(s) -> str:
    """Lower case, accents off, punctuation to spaces: 'Beyoncé - HALO!' -> 'beyonce halo'."""
    s = unicodedata.normalize("NFKD", str(s or "")).casefold()
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^\w]+", " ", s).split())


def iso_seconds(v) -> int | None:
    m = DUR_RE.match(str(v or ""))
    if not m or not any(m.groups()):
        return None
    d, h, mi, s = (int(x or 0) for x in m.groups())
    return d * 86400 + h * 3600 + mi * 60 + s


def _now() -> float:
    return time.time()


class Find:
    def __init__(self, listen, take, state_dir, get=None, one_read: str = "", one_bin: str = "one",
                 key: str = "", per_day: int = LIVE_PER_DAY, clock=_now):
        self.listen = listen
        self.take = take
        self.dir = Path(state_dir) / "find"
        self.one_read = one_read or str(Path.home() / ".local/bin/one-read")
        self.one_bin = one_bin
        self.key_pref = key
        self.per_day = per_day
        self.clock = clock
        self._get = get or self._one_get
        self._keys: tuple[float, list[str]] | None = None
        self.lock = threading.Lock()
        self._mem: dict | None = None

    # ---- YouTube through One (GET only) ----------------------------------------------------------------------
    def enabled(self) -> bool:
        if self._get != self._one_get:
            return True
        return bool(os.environ.get("ONE_SECRET")) and Path(self.one_read).exists()

    def _one_get(self, action: str, key: str, q: dict) -> dict:
        out = subprocess.run([self.one_read, "youtube-data", action, key, "--query-params", json.dumps(q)],
                             capture_output=True, text=True, timeout=60)
        try:
            d = json.loads(out.stdout)
        except ValueError:
            raise RuntimeError("One did not answer")
        r = d.get("response", d)
        if isinstance(r, dict) and "error" in r:
            err = r["error"]
            raise RuntimeError("YouTube refused: " + str(err.get("message", "") if isinstance(err, dict) else err)[:160])
        return r if isinstance(r, dict) else {}

    def _key(self) -> str:
        """The youtube-data connection to search through: CC_FIND_YT_KEY when it names one, else the first."""
        if self._get != self._one_get:
            return self.key_pref or "stub"
        now = self.clock()
        if not self._keys or now - self._keys[0] > KEYS_TTL:
            keys = []
            try:
                out = subprocess.run([self.one_bin, "--agent", "list"], capture_output=True, text=True, timeout=60)
                for c in json.loads(out.stdout).get("connections", []):
                    if c.get("platform") == "youtube-data" and c.get("state", "operational") == "operational" and c.get("key"):
                        keys.append(c["key"])
            except (OSError, ValueError, subprocess.SubprocessError):
                keys = []
            self._keys = (now, keys)
        keys = self._keys[1]
        if self.key_pref and any(k == self.key_pref or k.endswith(self.key_pref) for k in keys):
            return next(k for k in keys if k == self.key_pref or k.endswith(self.key_pref))
        return keys[0] if keys else ""

    # ---- the small cache on disk (queries a day, embed flags a week, the day's count) -------------------------
    def _cache(self) -> dict:
        if self._mem is None:
            try:
                self._mem = json.loads((self.dir / "cache.json").read_text())
            except (OSError, ValueError):
                self._mem = {}
            for k in ("q", "embed", "day"):
                if not isinstance(self._mem.get(k), dict):
                    self._mem[k] = {}
        return self._mem

    def _save(self) -> None:
        try:
            os.makedirs(self.dir, exist_ok=True)
            c = self._cache()
            now = self.clock()
            c["q"] = {k: v for k, v in c["q"].items() if now - v.get("t", 0) < QUERY_TTL}
            c["embed"] = {k: v for k, v in c["embed"].items() if now - v.get("t", 0) < EMBED_TTL}
            today = self._day()
            c["day"] = {today: c["day"].get(today, 0)}
            tmp = self.dir / ".cache.json.tmp"
            tmp.write_text(json.dumps(c, ensure_ascii=False))
            tmp.replace(self.dir / "cache.json")
        except OSError:
            pass

    def _day(self) -> str:
        return time.strftime("%Y-%m-%d", time.gmtime(self.clock()))

    def left(self) -> int:
        return max(0, self.per_day - int(self._cache()["day"].get(self._day(), 0)))

    # ---- embed flags --------------------------------------------------------------------------------------------
    def flags(self, ids: list[str]) -> None:
        """Fill the embed cache for these ids (one videos.list call per 50; part=status, then contentDetails)."""
        c = self._cache()
        now = self.clock()
        want = [i for i in dict.fromkeys(ids) if VID_RE.match(i) and now - c["embed"].get(i, {}).get("t", 0) >= EMBED_TTL]
        if not want or not self.enabled():
            return
        key = self._key()
        if not key:
            return
        for at in range(0, len(want), 50):
            chunk = want[at:at + 50]
            try:
                st = self._get(VIDEOS_ACTION, key, {"part": "status", "id": ",".join(chunk), "maxResults": 50})
            except RuntimeError:
                return
            try:
                cd = self._get(VIDEOS_ACTION, key, {"part": "contentDetails", "id": ",".join(chunk), "maxResults": 50})
            except RuntimeError:
                cd = {}
            durs = {v.get("id"): iso_seconds((v.get("contentDetails") or {}).get("duration")) for v in cd.get("items", []) if isinstance(v, dict)}
            region = {v.get("id"): region_why((v.get("contentDetails") or {}).get("regionRestriction")) for v in cd.get("items", []) if isinstance(v, dict)}
            seen = set()
            for v in st.get("items", []):
                if not isinstance(v, dict) or v.get("id") not in chunk:
                    continue
                s = v.get("status") or {}
                ok = bool(s.get("embeddable")) and s.get("privacyStatus") in ("public", "unlisted") and s.get("uploadStatus", "processed") == "processed"
                row = {"t": now, "embed": ok}
                if not ok:
                    row["why"] = WHY_OFF if s.get("privacyStatus") in ("public", "unlisted") else WHY_GONE
                elif region.get(v["id"]):
                    row = {"t": now, "embed": False, "why": region[v["id"]]}
                if durs.get(v["id"]):
                    row["dur"] = durs[v["id"]]
                c["embed"][v["id"]] = row
                seen.add(v["id"])
            for i in chunk:                      # asked for and not answered: removed
                if i not in seen:
                    c["embed"][i] = {"t": now, "embed": False, "why": WHY_GONE}

    def _mark(self, it: dict) -> dict:
        if it.get("k") != "yt":
            return {**it, "embed": True}
        f = self._cache()["embed"].get(it.get("id"))
        out = {**it, "embed": f["embed"] if f else None}
        if f and not f["embed"]:
            out["why"] = f.get("why", WHY_OFF)
        if f and f.get("dur") and not out.get("dur"):
            out["dur"] = f["dur"]
        return out

    # ---- the library already in the brain ---------------------------------------------------------------------
    def _stations(self) -> list[dict]:
        try:
            return self.listen._load()["stations"]
        except Exception:
            return []

    def library(self, q: str) -> list[dict]:
        words = norm(q).split()
        if not words:
            return []
        rank = {"own": 0, "likes": 1}
        sts = sorted(self._stations(), key=lambda s: rank.get(s.get("kind"), 2 if s.get("first") else 3))
        out, seen = [], set()
        for s in sts:
            sname = norm(s.get("name"))
            for it in s.get("items", []):
                key = (it.get("k"), it.get("id") or it.get("n"))
                if key in seen or it.get("k") not in ("yt", "file"):
                    continue
                hay = " ".join((norm(it.get("title")), norm(it.get("artist")), sname))
                if all(w in hay for w in words):
                    seen.add(key)
                    out.append({**it, "src": s.get("name", "")})
                    if len(out) >= LIBRARY_MAX:
                        return out
        return out

    def recent(self) -> list[dict]:
        out, seen = [], set()
        try:
            takes = self.take.state().get("takes", [])
        except Exception:
            takes = []
        for t in takes:
            o = t.get("over") or {}
            if o.get("kind") == "embed" and VID_RE.match(str(o.get("video_id") or "")):
                it = {"k": "yt", "id": o["video_id"], "title": o.get("title") or "", "artist": o.get("artist") or ""}
            elif o.get("kind") == "own" and o.get("n"):
                it = {"k": "file", "n": o["n"], "title": o.get("title") or "", "artist": o.get("artist") or ""}
            else:
                continue
            key = (it["k"], it.get("id") or it.get("n"))
            if key not in seen:
                seen.add(key)
                out.append({**it, "src": "recently used"})
            if len(out) >= RECENT_MAX:
                break
        return out

    def shortcuts(self) -> list[dict]:
        sts = self._stations()
        firsts = [s for s in sts if s.get("first")][:3]
        likes = [s for s in sts if s.get("kind") == "likes"]
        return [{"id": s["id"], "name": s.get("name", ""), "count": len(s.get("items", []))} for s in firsts + likes]

    # ---- the live search ----------------------------------------------------------------------------------------
    def live(self, q: str) -> dict:
        nq = norm(q)
        c = self._cache()
        hit = c["q"].get(nq)
        if hit and self.clock() - hit.get("t", 0) < QUERY_TTL:
            return {"ok": True, "items": hit["items"], "cached": True}
        if not self.enabled():
            return {"ok": False, "items": [], "why": "no YouTube account is connected to this brain (One)"}
        if self.left() <= 0:
            return {"ok": False, "items": [], "why": f"today's {self.per_day} YouTube searches are used (YouTube's daily limit); the library still answers"}
        key = self._key()
        if not key:
            return {"ok": False, "items": [], "why": "no YouTube account is connected to this brain (One)"}
        c["day"][self._day()] = int(c["day"].get(self._day(), 0)) + 1
        try:
            r = self._get(SEARCH_ACTION, key, {"part": "snippet", "type": "video", "q": str(q)[:120], "maxResults": LIVE_MAX})
        except RuntimeError as e:
            self._save()
            return {"ok": False, "items": [], "why": str(e)}
        items = []
        for x in r.get("items", []):
            vid = ((x.get("id") or {}) if isinstance(x, dict) else {}).get("videoId", "")
            sn = x.get("snippet") or {}
            if VID_RE.match(str(vid)):
                items.append({"k": "yt", "id": vid, "title": html.unescape(str(sn.get("title") or ""))[:200],
                              "artist": html.unescape(str(sn.get("channelTitle") or ""))[:120], "src": "YouTube"})
        c["q"][nq] = {"t": self.clock(), "items": items}
        return {"ok": True, "items": items}

    def check(self, vid) -> tuple[int, dict]:
        """One id's embed flag, asked when the owner picks a track whose flag is not known yet."""
        vid = str(vid or "")
        if not VID_RE.match(vid):
            return 400, {"ok": False, "error": "which video?"}
        with self.lock:
            self.flags([vid])
            it = self._mark({"k": "yt", "id": vid})
            self._save()
        return 200, {"ok": True, **{k: it[k] for k in ("id", "embed", "why", "dur") if k in it}}

    # ---- the door -----------------------------------------------------------------------------------------------
    def find(self, q, live=False) -> tuple[int, dict]:
        q = " ".join(str(q or "").split())[:120]
        with self.lock:
            lib = self.library(q)
            rec = self.recent() if not q else []
            lv = self.live(q) if (live and norm(q)) else None
            if lv is not None or rec:   # typing stays free and instant; the press (and recent) checks embedding
                self.flags([i["id"] for i in lib + rec + ((lv or {}).get("items") or []) if i.get("k") == "yt"])
            out = {"ok": True, "q": q, "recent": [self._mark(i) for i in rec], "shortcuts": self.shortcuts() if not q else [],
                   "library": [self._mark(i) for i in lib], "live": None, "live_left": self.left()}
            if lv is not None:
                out["live"] = {**lv, "items": [self._mark(i) for i in lv.get("items", [])]}
            self._save()
        return 200, out
