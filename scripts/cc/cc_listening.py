"""cc_listening.py: "Bring your listening" (YT-2, 2026-11-23).

The owner of this brain connects their own YouTube in One (a youtube-data connection on the One account
whose key is this brain's ONE_SECRET). One press on the home card then:

  1. reads, for every connected YouTube account: the liked videos (playlist LL), every playlist the
     account owns and every item in it, and each video's title, channel, category and length;
  2. keeps one listening record per video (deduplicated across likes and playlists) in this brain's own
     folder: <state>/listening/records.jsonl and listening.tsv;
  3. writes a short taste note (styles, artists, tempo where a title states it) and puts it into this
     brain's own memory through the normal upload door, so "Use my taste" (orfeo music room) and the
     reasoner can read it.

Every YouTube call is a GET through one-read (the wrapper whose .onerc allows reads only). Nothing is
written to YouTube, no audio or video is fetched, nothing is sent to any other brain or service. The
press is the owner's yes to the memory write, which the card's disclosure says before the press.
Standard library only.
"""
from __future__ import annotations

import collections
import json
import os
import re
import subprocess
import threading
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

# youtube-data actions in One (platform-wide ids, the same for every One account; read 2026-11-23).
ACTIONS = {
    "channels": "conn_mod_def::GKKPCBjQE60::zygriKUoRveDnsUAgdlwyA",
    "items": "conn_mod_def::GKKPD-ndjXw::3Jq2iL2zRrePHcrq9GV7yQ",
    "playlists": "conn_mod_def::GKKPEI4xYlI::mH9wDgN0R7eIRgRzWV5q7Q",
    "videos": "conn_mod_def::GKKPEyCYjmc::jTY7ENAyQ1uugwAPicQ3gg",
    "cats": "conn_mod_def::GKKPEuJeF0g::_e6GbSQTS5yKP1PqFpa0Ig",
}
ITEM_CAP = 10000          # per account, likes and playlist items together (about 200 reads)
NOTE_LAYERS = ("episodic", "semantic", "thinking")   # the first one this brain defines takes the note

# What the card says before the press (the disclosure), in the console's languages.
DISCLOSURE = {
    "en": ("What is read: your liked videos and your playlists on the YouTube accounts you connected in One "
           "(titles, channels, categories, lengths, when you added them). Why: so your brain knows what you "
           "listen to, can order the music room by your taste and answer about your music. Where it goes: into "
           "this brain only, a list in its own folder and one taste note in its memory. Nothing is sent "
           "anywhere else, nothing is written to YouTube, no audio is downloaded. Undo: delete the note in "
           "Knowledge and the folder listening/."),
    "el": ("Τι διαβάζεται: τα βίντεο που σου άρεσαν και οι λίστες σου στους λογαριασμούς YouTube που σύνδεσες "
           "στο One (τίτλοι, κανάλια, κατηγορίες, διάρκειες, πότε τα πρόσθεσες). Γιατί: για να ξέρει ο εγκέφαλός "
           "σου τι ακούς, να βάζει το μουσικό δωμάτιο στη σειρά του γούστου σου και να απαντά για τη μουσική σου. "
           "Πού πάει: μόνο σε αυτόν τον εγκέφαλο, μια λίστα στον φάκελό του και μια σημείωση γούστου στη μνήμη του. "
           "Τίποτα δεν στέλνεται αλλού, τίποτα δεν γράφεται στο YouTube, κανένας ήχος δεν κατεβαίνει. Αναίρεση: "
           "σβήσε τη σημείωση στο Knowledge και τον φάκελο listening/."),
    "ru": ("Что читается: понравившиеся видео и ваши плейлисты в аккаунтах YouTube, подключённых в One "
           "(названия, каналы, категории, длительность, когда добавлено). Зачем: чтобы ваш мозг знал, что вы "
           "слушаете, мог упорядочить музыкальную комнату по вашему вкусу и отвечать о вашей музыке. Куда: только "
           "в этот мозг, список в его папке и одна заметка о вкусе в его памяти. Ничего не отправляется наружу, "
           "ничего не пишется в YouTube, звук не скачивается. Отменить: удалите заметку в Knowledge и папку listening/."),
}

STYLES = [(s, re.compile(p, re.I)) for s, p in [
    ("afro house", r"afro ?house"), ("amapiano", r"amapiano"), ("melodic techno", r"melodic techno"),
    ("deep house", r"deep house"), ("tech house", r"tech house"), ("organic house", r"organic house"),
    ("techno", r"techno"), ("house", r"\bhouse\b|extended mix|club mix"), ("disco", r"disco"),
    ("drum and bass", r"drum ?(&|and|n) ?bass|\bdnb\b"), ("boom bap", r"boom ?bap"), ("trap", r"\btrap\b"),
    ("drill", r"\bdrill\b"), ("phonk", r"phonk"), ("lofi", r"lo-?fi"), ("type beat", r"type beat"),
    ("hip hop", r"hip ?hop|\brap\b"), ("r&b", r"r&b|rnb"), ("reggae", r"reggae"), ("jazz", r"jazz"),
    ("blues", r"blues"), ("rock", r"\brock\b"), ("soul", r"\bsoul\b"), ("pop", r"\bpop\b"), ("classical", r"classical|symphony|sonata"),
    ("piano", r"piano"), ("guitar", r"guitar"), ("violin", r"violin"), ("ambient", r"ambient"),
    ("remix", r"remix|re-?edit|bootleg"), ("dj set", r"dj set|live set|boiler room|cercle|mixtape"),
    ("instrumental", r"instrumental"), ("live", r"\blive\b"), ("folk", r"\bfolk\b|laiko|rebetiko|ρεμπέτικο|λαϊκ"),
]]
BPM = re.compile(r"(\d{2,3})\s*bpm|bpm\s*(\d{2,3})", re.I)


def _iso_secs(iso: str) -> int | None:
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    if not m:
        return None
    d, h, mi, s = (int(x or 0) for x in m.groups())
    return ((d * 24 + h) * 60 + mi) * 60 + s


def _artist(channel: str, title: str) -> str:
    if channel.endswith(" - Topic"):
        return channel[:-8]
    m = re.match(r"^\s*([^\-–—|]{2,60}?)\s+[-–—]\s+", title)
    if m and "type beat" not in title.lower():
        return m.group(1).strip()
    return channel


class Listening:
    def __init__(self, folder: Path, one_read: str = "", one_bin: str = "one",
                 api_url: str = "", api_key: str = ""):
        self.dir = Path(folder)
        self.one_read = one_read or str(Path.home() / ".local/bin/one-read")
        self.one_bin = one_bin
        self.api_url, self.api_key = api_url.rstrip("/"), api_key
        self.lock = threading.Lock()
        self.running = False
        self.error = ""

    # ---------- One (reads only) ----------
    def enabled(self) -> bool:
        return bool(os.environ.get("ONE_SECRET")) and Path(self.one_read).exists()

    def _get(self, action: str, key: str, q: dict) -> dict:
        out = subprocess.run([self.one_read, "youtube-data", ACTIONS[action], key, "--query-params", json.dumps(q)],
                             capture_output=True, text=True, timeout=120)
        try:
            d = json.loads(out.stdout)
        except Exception:
            raise RuntimeError(f"One did not answer for {action}")
        r = d.get("response", d)
        if isinstance(r, dict) and "error" in r:
            raise RuntimeError(f"YouTube refused {action}: {str(r['error'].get('message', ''))[:160]}")
        return r

    def _paged(self, action: str, key: str, q: dict, cap: int) -> list:
        items, tok = [], None
        while len(items) < cap:
            qq = dict(q, maxResults=50)
            if tok:
                qq["pageToken"] = tok
            r = self._get(action, key, qq)
            items += r.get("items", [])
            tok = r.get("nextPageToken")
            if not tok:
                break
        return items[:cap]

    def accounts(self) -> list[dict]:
        """The youtube-data connections on this brain's One account, each named by its own channel."""
        if not self.enabled():
            return []
        try:
            out = subprocess.run([self.one_bin, "--agent", "list"], capture_output=True, text=True, timeout=60)
            conns = json.loads(out.stdout).get("connections", [])
        except Exception:
            return []
        acc = []
        for c in conns:
            if c.get("platform") != "youtube-data" or c.get("state", "operational") != "operational":
                continue
            key = c.get("key", "")
            try:
                ch = self._get("channels", key, {"part": "snippet", "mine": True}).get("items", [])
            except RuntimeError:
                ch = []
            sn = ch[0]["snippet"] if ch else {}
            acc.append({"key": key, "tail": key[-6:], "channel": sn.get("title", ""), "handle": sn.get("customUrl", "")})
        return acc

    # ---------- state ----------
    def state(self, with_accounts: bool = True) -> dict:
        last = {}
        p = self.dir / "last.json"
        if p.is_file():
            try:
                last = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                last = {}
        acc = [{k: a[k] for k in ("tail", "channel", "handle")} for a in self.accounts()] if with_accounts else None
        return {"one": self.enabled(), "accounts": acc, "running": self.running, "error": self.error,
                "last": last or None, "disclosure": DISCLOSURE}

    # ---------- the read ----------
    def start(self) -> tuple[int, dict]:
        with self.lock:
            if self.running:
                return 409, {"ok": False, "error": "already reading"}
            if not self.enabled():
                return 400, {"ok": False, "error": "One is not set up on this brain"}
            self.running, self.error = True, ""
        threading.Thread(target=self._run, daemon=True).start()
        return 202, {"ok": True, "running": True}

    def _run(self) -> None:
        try:
            self.read()
        except Exception as e:  # noqa: BLE001
            self.error = str(e)[:300]
        finally:
            self.running = False

    def read(self) -> dict:
        acc = self.accounts()
        if not acc:
            raise RuntimeError("no YouTube account is connected in One yet")
        rec: dict[str, dict] = {}
        per = []
        for a in acc:
            key, name = a["key"], a["channel"] or a["tail"]
            likes = self._paged("items", key, {"part": "snippet", "playlistId": "LL"}, ITEM_CAP)
            pls = self._paged("playlists", key, {"part": "snippet", "mine": True}, 1000)
            budget, n_items = ITEM_CAP - len(likes), 0
            entries = [(i, None) for i in likes]
            for p in pls:
                if budget <= 0:
                    break
                its = self._paged("items", key, {"part": "snippet", "playlistId": p["id"]}, budget)
                budget -= len(its); n_items += len(its)
                entries += [(i, p["snippet"].get("title", "")) for i in its]
            ids = sorted({i["snippet"]["resourceId"]["videoId"] for i, _ in entries})
            vids: dict[str, dict] = {}
            for part in ("snippet", "contentDetails"):   # One's passthrough keeps one part per call
                for n in range(0, len(ids), 50):
                    r = self._get("videos", key, {"part": part, "id": ",".join(ids[n:n + 50]), "maxResults": 50})
                    for v in r.get("items", []):
                        vids.setdefault(v["id"], {})[part] = v[part]
            cats = {c["id"]: c["snippet"]["title"] for c in self._get("cats", key, {"part": "snippet", "regionCode": "US"}).get("items", [])}
            for i, pl in entries:
                vid = i["snippet"]["resourceId"]["videoId"]
                v = vids.get(vid, {}); sn = v.get("snippet", {})
                title = (sn.get("title") or i["snippet"].get("title", "")).strip()
                ch = sn.get("channelTitle", "")
                r = rec.setdefault(vid, {"video_id": vid, "title": title, "channel": ch, "artist": _artist(ch, title) if sn else "",
                                         "category": cats.get(sn.get("categoryId", ""), ""), "available": bool(sn),
                                         "seconds": _iso_secs(v.get("contentDetails", {}).get("duration", "")),
                                         "liked": False, "playlists": [], "accounts": [], "added": []})
                if name not in r["accounts"]:
                    r["accounts"].append(name)
                r["added"].append((i["snippet"].get("publishedAt") or "")[:10])
                if pl is None:
                    r["liked"] = True
                elif pl not in r["playlists"]:
                    r["playlists"].append(pl)
            per.append({"channel": name, "likes": len(likes), "playlists": len(pls), "items": n_items})
        for r in rec.values():
            hay = r["title"] + " " + r["channel"] + " " + " ".join(r["playlists"])
            r["styles"] = [s for s, rx in STYLES if rx.search(hay)]
            m = BPM.search(r["title"])
            b = int(m.group(1) or m.group(2)) if m else None
            r["bpm"] = b if b and 50 <= b <= 200 else None
            r["music"] = r["available"] and (r["category"] == "Music" or r["channel"].endswith(" - Topic") or bool(r["styles"]))
        self.dir.mkdir(parents=True, exist_ok=True)
        with open(self.dir / "records.jsonl", "w", encoding="utf-8") as f:
            for r in rec.values():
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        with open(self.dir / "listening.tsv", "w", encoding="utf-8") as f:
            f.write("video_id\ttitle\tchannel\tartist\tcategory\tmusic\tstyles\tbpm\tliked\tplaylists\tfirst_added\tlink\n")
            for r in sorted(rec.values(), key=lambda r: max(r["added"] or [""]), reverse=True):
                cl = lambda s: str(s or "").replace("\t", " ").replace("\n", " ")
                f.write("\t".join(cl(x) for x in [r["video_id"], r["title"], r["channel"], r["artist"], r["category"],
                                                  "yes" if r["music"] else "no", ", ".join(r["styles"]), r["bpm"] or "",
                                                  "yes" if r["liked"] else "no", "; ".join(r["playlists"]),
                                                  min(r["added"] or [""]), "https://www.youtube.com/watch?v=" + r["video_id"]]) + "\n")
        note, words = taste_note(list(rec.values()), per)
        (self.dir / "taste.md").write_text(note, encoding="utf-8")
        doc = self._keep_note(note)
        last = {"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "accounts": per,
                "records": len(rec), "music": sum(r["music"] for r in rec.values()),
                "taste": words, "note": doc}
        (self.dir / "last.json").write_text(json.dumps(last, ensure_ascii=False), encoding="utf-8")
        return last

    # ---------- into this brain's own memory ----------
    def _api(self, method: str, route: str, data: bytes | None = None, ctype: str = "application/json") -> tuple[int, dict]:
        req = urllib.request.Request(self.api_url + route, data=data, method=method,
                                     headers={"X-API-Key": self.api_key, "Content-Type": ctype})
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                body = r.read()
                return r.status, (json.loads(body) if body.strip()[:1] in (b"{", b"[") else {})
        except urllib.error.HTTPError as e:
            try:
                return e.code, json.loads(e.read())
            except Exception:
                return e.code, {}
        except Exception:
            return 0, {}

    @staticmethod
    def _multipart(fields: dict, fname: str = "", content: bytes = b"") -> tuple[bytes, str]:
        b = "----listening-" + uuid.uuid4().hex
        out = bytearray()
        for k, v in fields.items():
            out += f"--{b}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode()
        if fname:
            out += (f"--{b}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{fname}\"\r\n"
                    "Content-Type: text/markdown\r\n\r\n").encode() + content + b"\r\n"
        out += f"--{b}--\r\n".encode()
        return bytes(out), f"multipart/form-data; boundary={b}"

    def _keep_note(self, note: str) -> dict:
        """Permit, upload (a proposal), approve when the injection scan is clean, ingest. The owner's press
        on the card is the yes; a flagged scan is left waiting in Knowledge for them."""
        if not (self.api_url and self.api_key):
            return {"kept": False, "why": "this bridge holds no brain key"}
        name = "my-listening-taste-" + time.strftime("%Y-%m-%d") + ".md"
        last_err = ""
        for layer in NOTE_LAYERS:
            c, j = self._api("POST", "/documents/upload/permit")
            if c != 200 or "permit_id" not in j:
                return {"kept": False, "why": f"the brain gave no upload permit ({c})"}
            body, ct = self._multipart({"permit_id": j["permit_id"], "layer": layer}, name, note.encode())
            c, j2 = self._api("POST", "/documents/upload", body, ct)
            if c == 202 and j2.get("proposal_id"):
                risk = (j2.get("injection_scan") or {}).get("risk")
                if risk not in (None, "none", "low"):
                    return {"kept": False, "why": "waiting for your yes in Knowledge (the scan flagged it)", "name": name, "layer": layer}
                self._api("POST", "/documents/approve-all", json.dumps({"proposal_ids": [j2["proposal_id"]]}).encode())
                return {"kept": True, "name": name, "layer": layer}
            last_err = str((j2.get("error") or {}).get("message", "") or j2)[:160]
            if "layer" not in last_err.lower():
                break
        return {"kept": False, "why": last_err or "upload refused"}


def taste_note(records: list[dict], per: list[dict]) -> tuple[str, list[str]]:
    """A plain note the brain's memory search finds for 'music I like': styles, artists, tempo, counts."""
    music = [r for r in records if r.get("music")]
    st = collections.Counter(s for r in music for s in r.get("styles", []))
    art = collections.Counter(r["artist"] for r in music if r.get("artist"))
    liked = collections.Counter(r["artist"] for r in music if r.get("liked") and r.get("artist"))
    bpms = sorted(r["bpm"] for r in music if r.get("bpm"))
    months = collections.Counter(a[:7] for r in records for a in r.get("added", []) if a)
    lines = [
        "---", f"created: {time.strftime('%Y-%m-%d')}", "source: my YouTube likes and playlists, read through One (GET only)", "---", "",
        "# Music I like: my listening taste", "",
        "Music I like, from my YouTube likes and playlists: " + "; ".join(
            f"{p['channel']}: {p['likes']} likes, {p['playlists']} playlists, {p['items']} playlist items" for p in per)
        + f". {len(records)} distinct videos, {len(music)} of them music. Titles and channels only; no audio was analysed.", "",
        "## Genres and styles, most first", "",
        ", ".join(f"{s} ({n})" for s, n in st.most_common(14)) or "no style words in the titles yet", "",
        "## Artists", "",
        "Most present: " + (", ".join(a for a, _ in art.most_common(20)) or "none yet") + ".",
    ]
    if liked:
        lines.append("Most liked: " + ", ".join(a for a, _ in liked.most_common(10)) + ".")
    lines += ["", "## Tempo", ""]
    lines.append(f"{len(bpms)} titles state a tempo, median {bpms[len(bpms) // 2]} BPM." if bpms
                 else "No title states a tempo; tempo is unknown without listening.")
    if months:
        top = sorted(months.items(), key=lambda kv: -kv[1])[:3]
        lines += ["", "## When", "", "Most added in " + ", ".join(f"{m} ({n})" for m, n in sorted(top)) + "."]
    return "\n".join(lines) + "\n", [s for s, _ in st.most_common(8)]
