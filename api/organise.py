"""Your map (ORGANISE-1, 2026-11-26): after the move-in, the brain reads what it holds and proposes the
person's own areas.

hbar 2026-11-26: "analyze all these files and organize all these into appropriate categorization ... one
coherent organized mental structure (anne.world folder, like hbar.world)". The move-in ended on a count; this
ends it on a map.

What it reads, cheap first: every remembered document's name (laptop files keep their old folder path,
`laptop/<Folder>/<path>`), its title or first chunk, the conversation records of imported chats (title, dates,
extractive summary), and the embeddings already stored (one mean vector per document). No model reads a
document. One model call names the areas (top words and a few titles per area); without a model, or when the
call fails, the person's own folder names and words name them.

The pieces, all pure but the store:
- `build(items, ...)`: 4 to 9 areas (plus an archive of old items when there are enough), each with a count,
  three examples, the item names and one line. Old chats and laptop files on the same subject meet through
  the embedding and the shared words of their titles and folders.
- edits before the yes: `rename`, `merge`, `move`. Nothing is labelled before `accept`.
- `accept`: every document of an area gets `metadata.area` (retrieval and the Knowledge page filter by it);
  the previous labels are kept for `undo`. Where the member has a hands user, `write_world` writes
  `<name>.world/` (one folder per area, an index.md listing its documents and chats); files stay where they are.
- `assign`: a document that arrives after the yes goes to the nearest area, or to `unsorted` when none is near.

The store is an interface (`PgStore` over document_embeddings; tests use a store in memory), so every rule
here is tested without a database. Logic tests: tests/test_organise.py (a made-up student only).
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import time
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional

try:
    import numpy as np
except ImportError:  # pragma: no cover - the api image has numpy
    np = None

UNSORTED = "unsorted"
ARCHIVE_YEARS = 3          # an item last touched this many years before the newest is archive
MIN_AREAS, MAX_AREAS = 4, 9
MIN_DOCS = 12              # fewer remembered documents: no map is proposed yet
ASSIGN_MIN = 0.22          # cosine to the nearest area below this: unsorted
STEM = 6                   # words are cut to this many letters (light stemming across inflections)
EXAMPLES = 3
NAME_TITLES = 8            # titles per area sent to the namer
ITEMS_LISTED = 400         # item names kept per area in the proposal (the count stays exact)

# Words that say nothing about a subject: folder furniture, file kinds, AI names, function words of the
# languages a member brain is likely to see. Kept short on purpose; the tf-idf does the rest.
_STOP = set("""
laptop documents document desktop downloads download google drive dropbox onedrive icloud clouddocs mobile users user
home files file folder new copy final draft untitled scan image img pdf docx doc txt md rtf pages odt xlsx csv pptx key
chat chats chatgpt claude gemini codex copilot conversation conversations pasted export notes note misc stuff other
first last ask asks turns turn thanks thank please help
the and for with from that this what how why are was were you your our not but all can about into over more some any
der die das und mit von fur für ist ein eine einer den dem des zum zur auf aus bei wie was nicht oder auch noch
el la los las del con por para una uno que como mas más sus est
le les des une pour avec dans sur pas qui que
и в во на не что как это с со по для из к у о от за же то но а или
""".split())

_WORD = re.compile(r"[^\W\d_]{3,}", re.UNICODE)
_YEAR = re.compile(r"(?<!\d)(19[89]\d|20[0-4]\d)(?!\d)")
_ARCHIVE_WORDS = {"archive", "archiv", "archivo", "archives", "old", "alt", "alte", "viejo", "архив", "старое"}


def _fold(s: str) -> str:
    """Lowercase without accents (é -> e, ü -> u); Cyrillic stays Cyrillic."""
    s = unicodedata.normalize("NFKD", s.lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def words(text: str) -> List[str]:
    return [w for w in _WORD.findall(_fold(text or "")) if w not in _STOP]


def stem(w: str) -> str:
    return w[:STEM]


def folders_of(name: str) -> List[str]:
    """The old folders of a document name: `laptop/Documents/Uni/Biologie/zelle.md` -> [Uni, Biologie].
    The `laptop/` prefix and the home's standard folders say nothing about the subject."""
    parts = [p for p in str(name or "").split("/")[:-1] if p]
    out = []
    for p in parts:
        if _fold(p) in _STOP or p.startswith("."):
            continue
        out.append(p)
    return out


def date_of(item: dict) -> Optional[str]:
    """The item's own date (ISO day): a chat's last turn, else a year in its name or title."""
    d = item.get("date")
    if d:
        return str(d)[:10]
    m = _YEAR.search(f"{item.get('name', '')} {item.get('title', '')}")
    return f"{m.group(1)}-06-30" if m else None


def _title_of(item: dict) -> str:
    t = (item.get("title") or "").strip()
    if t:
        return t[:160]
    base = str(item.get("name") or "").rsplit("/", 1)[-1]
    base = re.sub(r"\.[A-Za-z0-9]{1,5}$", "", base)
    base = re.sub(r"^(claude-code|codex|chatgpt|claude|gemini|deepseek|grok|copilot|perplexity|lechat|pasted)_", "", base)
    return re.sub(r"[_\-]+", " ", base).strip()[:160] or str(item.get("name"))


# ---------------------------------------------------------------- features

class Features:
    """tf-idf over the stems of folders (weight 3), title (2) and summary (1), joined with the stored
    embedding. Fitted on the items of one map; kept with the accepted map so arrivals use the same space."""

    def __init__(self, vocab: Dict[str, int], idf: List[float], surface: Dict[str, str], emb_dim: int):
        self.vocab, self.idf, self.surface, self.emb_dim = vocab, idf, surface, emb_dim

    @staticmethod
    def counts(item: dict) -> Counter:
        c: Counter = Counter()
        for f in folders_of(item.get("name", "")):
            for w in words(f):
                c[stem(w)] += 3.0
        for w in words(_title_of(item)):
            c[stem(w)] += 2.0
        for w in words((item.get("summary") or "")[:600]):
            c[stem(w)] += 1.0
        return c

    @classmethod
    def fit(cls, items: List[dict]) -> "Features":
        df: Counter = Counter()
        surf: Dict[str, Counter] = defaultdict(Counter)
        for it in items:
            seen = set()
            for f in folders_of(it.get("name", "")):
                for w in _WORD.findall(f):
                    if _fold(w) not in _STOP:
                        surf[stem(_fold(w))][w] += 3
            for w in _WORD.findall(_title_of(it)):
                if _fold(w) not in _STOP:
                    surf[stem(_fold(w))][w] += 1
            for s in cls.counts(it):
                seen.add(s)
            df.update(seen)
        n = max(1, len(items))
        hi = max(2, int(0.5 * n))
        keep = sorted(s for s, d in df.items() if d >= 2 and d <= hi) or sorted(df)
        vocab = {s: i for i, s in enumerate(keep)}
        idf = [math.log((1 + n) / (1 + df[s])) + 1.0 for s in keep]
        surface = {s: surf[s].most_common(1)[0][0] if surf.get(s) else s for s in keep}
        dims = {len(it["vec"]) for it in items if it.get("vec") is not None}
        return cls(vocab, idf, surface, max(dims) if dims else 0)

    def text_vec(self, item: dict):
        v = np.zeros(len(self.vocab))
        for s, c in self.counts(item).items():
            j = self.vocab.get(s)
            if j is not None:
                v[j] = (1 + math.log(c)) * self.idf[j]
        n = np.linalg.norm(v)
        return v / n if n else v

    def emb_vec(self, item: dict):
        if not self.emb_dim:
            return np.zeros(0)
        e = item.get("vec")
        if e is None or len(e) != self.emb_dim:
            return np.zeros(self.emb_dim)
        e = np.asarray(e, dtype=float)
        n = np.linalg.norm(e)
        return e / n if n else e

    def matrix(self, items: List[dict]):
        rows = []
        for it in items:
            t, e = self.text_vec(it), self.emb_vec(it)
            r = np.concatenate([t, e]) if e.size else t
            n = np.linalg.norm(r)
            rows.append(r / n if n else r)
        return np.vstack(rows) if rows else np.zeros((0, len(self.vocab) + self.emb_dim))

    def to_json(self) -> dict:
        return {"vocab": list(self.vocab), "idf": self.idf, "surface": self.surface, "emb_dim": self.emb_dim}

    @classmethod
    def from_json(cls, d: dict) -> "Features":
        return cls({s: i for i, s in enumerate(d["vocab"])}, d["idf"], d.get("surface", {}), d.get("emb_dim", 0))


# ---------------------------------------------------------------- clustering

def _kmeans(X, k: int, seed: int = 0, iters: int = 40):
    """Spherical k-means, k-means++ seeding, fixed seed: the same holdings give the same map."""
    rng = np.random.RandomState(seed)
    n = X.shape[0]
    first = rng.randint(n)
    C = [X[first]]
    d2 = 1.0 - X @ X[first]
    for _ in range(1, k):
        p = np.clip(d2, 0, None)
        p = p / p.sum() if p.sum() > 0 else np.full(n, 1.0 / n)
        c = X[rng.choice(n, p=p)]
        C.append(c)
        d2 = np.minimum(d2, 1.0 - X @ c)
    C = np.vstack(C)
    lab = np.zeros(n, dtype=int)
    for _ in range(iters):
        new = np.argmax(X @ C.T, axis=1)
        if _ and np.array_equal(new, lab):
            break
        lab = new
        for j in range(k):
            m = X[lab == j]
            if len(m):
                c = m.sum(axis=0)
                nn = np.linalg.norm(c)
                C[j] = c / nn if nn else c
    inertia = float(np.sum(1.0 - np.sum(X * C[lab], axis=1)))
    return lab, C, inertia


def _silhouette(X, lab, k: int, sample: int = 600, seed: int = 0) -> float:
    n = X.shape[0]
    idx = np.arange(n)
    if n > sample:
        idx = np.random.RandomState(seed).choice(n, sample, replace=False)
    D = 1.0 - X[idx] @ X.T
    s = []
    for row, i in enumerate(idx):
        own = lab == lab[i]
        if own.sum() <= 1:
            s.append(0.0)
            continue
        a = D[row, own].sum() / (own.sum() - 1)
        b = min((D[row, lab == j].mean() for j in range(k) if j != lab[i] and (lab == j).any()), default=0.0)
        s.append((b - a) / max(a, b) if max(a, b) > 0 else 0.0)
    return float(np.mean(s)) if s else 0.0


def cluster(X, kmin: int, kmax: int):
    """The k in kmin..kmax with the best silhouette (six seeds each, the lowest inertia kept; three seeds
    fell into a local minimum on the test student and merged two subjects)."""
    best = None
    n = X.shape[0]
    for k in range(kmin, min(kmax, n) + 1):
        runs = [_kmeans(X, k, seed=s) for s in range(6)]
        lab, C, _ = min(runs, key=lambda r: r[2])
        sc = _silhouette(X, lab, k)
        if best is None or sc > best[0] + 1e-9:
            best = (sc, lab, C)
    return best[1], best[2]


def _merge_small(X, lab, C, floor: int):
    """Areas under `floor` items join their nearest neighbour; the labels are renumbered 0..k-1."""
    while True:
        sizes = Counter(lab.tolist())
        small = [j for j, n in sizes.items() if n < floor]
        if not small or len(sizes) <= 1:
            break
        j = min(small, key=lambda x: sizes[x])
        others = [o for o in sizes if o != j]
        to = max(others, key=lambda o: float(C[j] @ C[o]))
        lab = np.where(lab == j, to, lab)
    keep = sorted(set(lab.tolist()))
    remap = {o: i for i, o in enumerate(keep)}
    lab = np.array([remap[x] for x in lab.tolist()])
    C2 = []
    for i in range(len(keep)):
        c = X[lab == i].sum(axis=0)
        nn = np.linalg.norm(c)
        C2.append(c / nn if nn else c)
    return lab, np.vstack(C2)


# ---------------------------------------------------------------- naming

def _area_terms(feat: Features, X, lab, j: int, n_terms: int = 6) -> List[str]:
    """The words that set area j apart: its mean tf-idf weight less the corpus mean, in the person's
    own spelling (the most frequent surface form, folder names first)."""
    T = X[:, :len(feat.vocab)]
    if not T.shape[1]:
        return []
    inside = T[lab == j].mean(axis=0)
    score = inside - T.mean(axis=0) * 0.5
    order = np.argsort(-score)
    inv = {i: s for s, i in feat.vocab.items()}
    out = []
    for i in order[: n_terms * 3]:
        if inside[i] <= 0:
            break
        w = feat.surface.get(inv[i], inv[i])
        if w.lower() not in [o.lower() for o in out]:
            out.append(w)
        if len(out) >= n_terms:
            break
    return out


def _folder_name(members: List[dict]) -> Optional[str]:
    """The old folder most of an area's laptop files came from, when one clearly leads (over 40%)."""
    c: Counter = Counter()
    for it in members:
        fs = folders_of(it.get("name", ""))
        if fs:
            c[fs[-1]] += 1
    if not c:
        return None
    name, n = c.most_common(1)[0]
    return name if n >= 0.4 * len(members) else None


WORDS = {
    "en": {"line": "Notes and chats about {terms}.", "archive": "Archive", "archive_line": "Older things, kept: before {year}.",
           "unsorted": "Unsorted"},
    "ru": {"line": "Заметки и чаты: {terms}.", "archive": "Архив", "archive_line": "Старое, сохранено: до {year} года.",
           "unsorted": "Не разобрано"},
    "de": {"line": "Notizen und Chats zu {terms}.", "archive": "Archiv", "archive_line": "Älteres, aufbewahrt: vor {year}.",
           "unsorted": "Unsortiert"},
}


def _w(lang: str) -> dict:
    return WORDS.get((lang or "en")[:2], WORDS["en"])


def fallback_name(terms: List[str], members: List[dict], lang: str) -> dict:
    name = _folder_name(members) or ((terms[0] if terms[0] != terms[0].lower() else terms[0].capitalize()) if terms else "Area")
    rest = [t for t in terms if t.lower() != name.lower()][:3]
    return {"name": name[:40], "line": _w(lang)["line"].format(terms=", ".join(rest or [name]))}


def namer_prompt(areas: List[dict], lang: str) -> str:
    lines = []
    for a in areas:
        lines.append(f"Area {a['id']} ({a['count']} items). Words: {', '.join(a['terms']) or '-'}. "
                     f"Old folders: {', '.join(a['folders']) or '-'}. Titles: " + " | ".join(a["titles"]))
    return ("You are naming the areas of one person's files and old AI chats, so they recognise their own world.\n"
            "For each area give a short name (one to three words) and one plain line on what goes there.\n"
            "Use the person's own words: the language most of the titles and folder names are in, their subject "
            "names (for a student, the subject; diary and life things are 'personal' in their language). "
            f"The person reads the console in '{lang}'. Never invent a subject the titles do not show.\n"
            "Answer with JSON only: [{\"id\": \"a1\", \"name\": \"...\", \"line\": \"...\"}, ...]\n\n"
            + "\n".join(lines))


def parse_names(raw: str, ids: Iterable[str]) -> Dict[str, dict]:
    """The namer's JSON, checked: known ids only, plain text, capped; anything else is dropped."""
    ids = set(ids)
    m = re.search(r"\[.*\]", raw or "", re.S)
    if not m:
        return {}
    try:
        data = json.loads(m.group(0))
    except ValueError:
        return {}
    out = {}
    for d in data if isinstance(data, list) else []:
        if not isinstance(d, dict) or d.get("id") not in ids:
            continue
        name = _plain(d.get("name"), 40)
        line = _plain(d.get("line"), 160)
        if name:
            out[d["id"]] = {"name": name, "line": line}
    return out


def _plain(s: Any, n: int) -> str:
    s = re.sub(r"<[^>]*>|[`*_#\[\]{}]", "", str(s or ""))
    return re.sub(r"\s+", " ", s).strip()[:n]


# ---------------------------------------------------------------- the proposal

def _newest_year(items: List[dict]) -> Optional[int]:
    ys = [int(d[:4]) for d in (date_of(i) for i in items) if d]
    return max(ys) if ys else None


def is_archive(item: dict, cutoff_year: Optional[int]) -> bool:
    """Old by its own date, or kept in a top folder the person called archive. An `Alt/` inside a subject
    folder stays with the subject."""
    fs = folders_of(item.get("name", ""))
    if fs and _fold(fs[0]) in _ARCHIVE_WORDS:
        return True
    d = date_of(item)
    return bool(cutoff_year and d and int(d[:4]) < cutoff_year)


def build(items: List[dict], lang: str = "en", namer: Optional[Callable[[str], Optional[str]]] = None,
          now: Optional[float] = None) -> dict:
    """The proposal. `items`: [{name, kind 'doc'|'chat', title, summary, date, vec, private}].
    `namer(prompt) -> text` is called once for the whole map, never per document; private items' titles are
    never put in its prompt."""
    if np is None:
        raise RuntimeError("numpy is needed to build a map")
    items = sorted((dict(i) for i in items if i.get("name")), key=lambda i: i["name"])   # the same holdings, the same map
    n = len(items)
    if n < MIN_DOCS:
        return {"state": "too_few", "total": n, "need": MIN_DOCS}
    newest = _newest_year(items)
    cutoff = newest - ARCHIVE_YEARS + 1 if newest else None
    arch = [it for it in items if is_archive(it, cutoff)]
    if len(arch) < max(5, 0.03 * n):
        arch = []
    arch_names = {a["name"] for a in arch}
    live = [it for it in items if it["name"] not in arch_names]
    kmax = MAX_AREAS - (1 if arch else 0)
    kmin = min(MIN_AREAS - (1 if arch else 0), max(1, len(live) // 3))
    feat = Features.fit(items)
    X = feat.matrix(live)
    lab, C = cluster(X, max(1, kmin), max(1, kmax))
    lab, C = _merge_small(X, lab, C, floor=max(3, int(0.02 * len(live))))
    if len(set(lab.tolist())) < kmin and len(live) >= kmin * 3:
        lab, C = cluster(X, kmin, kmin)   # merging went under the floor: take kmin as it comes

    areas = []
    for j in range(C.shape[0]):
        idx = np.where(lab == j)[0]
        members = [live[i] for i in idx]
        sims = X[idx] @ C[j]
        order = [members[i] for i in np.argsort(-sims)]
        terms = _area_terms(feat, X, lab, j)
        areas.append({"id": f"a{j + 1}", "members": order, "terms": terms, "centroid": C[j]})
    if arch:
        Xa = feat.matrix(arch)
        ca = Xa.sum(axis=0)
        ca = ca / (np.linalg.norm(ca) or 1.0)
        areas.append({"id": "archive", "members": arch, "terms": [], "centroid": ca, "archive": True})

    # name: one call for the whole map
    w = _w(lang)
    briefs = []
    for a in areas:
        if a.get("archive"):
            continue
        open_titles = [_title_of(m) for m in a["members"] if not m.get("private")][:NAME_TITLES]
        folders = [f for f, _ in Counter(f for m in a["members"] for f in folders_of(m["name"])[-1:]).most_common(3)]
        briefs.append({"id": a["id"], "count": len(a["members"]), "terms": a["terms"], "folders": folders, "titles": open_titles})
    named: Dict[str, dict] = {}
    model_named = False
    if namer and briefs:
        try:
            raw = namer(namer_prompt(briefs, lang))
            named = parse_names(raw or "", [b["id"] for b in briefs])
            model_named = bool(named)
        except Exception:  # noqa: BLE001 - the person's own words stand
            named = {}
    out_areas = []
    used = set()
    for a in areas:
        if a.get("archive"):
            nm = {"name": w["archive"], "line": w["archive_line"].format(year=cutoff or "")}
        else:
            nm = named.get(a["id"]) or fallback_name(a["terms"], a["members"], lang)
        name = nm["name"]
        k = 2
        while name.lower() in used:
            name = f"{nm['name']} {k}"; k += 1
        used.add(name.lower())
        out_areas.append(_area_out(a, name, nm.get("line") or "", a.get("archive", False)))
    out_areas.sort(key=lambda x: (x.get("archive", False), -x["count"]))
    t = now or time.time()
    prop = {
        "state": "proposed", "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t)), "lang": lang,
        "total": n, "docs": sum(1 for i in items if i.get("kind") != "chat"), "chats": sum(1 for i in items if i.get("kind") == "chat"),
        "model_named": model_named, "areas": out_areas,
        "titles": {i["name"]: {"title": _title_of(i), "kind": i.get("kind", "doc")} for i in items},
    }
    prop["id"] = proposal_id(prop)
    prop["_space"] = {"features": feat.to_json(),
                      "centroids": {a["id"]: a["centroid"].round(5).tolist() for a in areas}}
    return prop


def _area_out(a: dict, name: str, line: str, archive: bool) -> dict:
    members = a["members"]
    ex = []
    chats = [m for m in members if m.get("kind") == "chat"]
    docs = [m for m in members if m.get("kind") != "chat"]
    # three examples near the middle of the area; one of them a chat when the area holds chats and files
    seen = set()

    def take(ms, n):
        for m in ms:
            t = _title_of(m)
            if len([e for e in ex if e["kind"] == m.get("kind", "doc")]) >= n or t.lower() in seen:
                continue
            seen.add(t.lower())
            ex.append({"name": m["name"], "title": t, "kind": m.get("kind", "doc")})
    if chats and docs:
        take(docs, 2); take(chats, 1)
    take(members, EXAMPLES)
    ex = ex[:EXAMPLES]
    return {"id": a["id"], "name": name, "line": line, "count": len(members), "docs": len(docs), "chats": len(chats),
            "examples": ex, "items": [m["name"] for m in members], "archive": archive}


def proposal_id(prop: dict) -> str:
    """A short hash of what the yes is for: every area's name and items. An edit changes it."""
    h = hashlib.sha256()
    for a in prop.get("areas", []):
        h.update(a["id"].encode()); h.update(b"\0"); h.update(a["name"].encode()); h.update(b"\0")
        for it in sorted(a["items"]):
            h.update(it.encode()); h.update(b"\n")
    return "map_" + h.hexdigest()[:12]


def public(prop: dict, items_per_area: int = 0) -> dict:
    """The proposal as the home reads it: no feature space; at most `items_per_area` item names (0 = none)."""
    out = {k: v for k, v in prop.items() if not k.startswith("_") and k != "titles"}
    areas = []
    for a in prop.get("areas", []):
        b = dict(a)
        b["items"] = a["items"][:items_per_area] if items_per_area else []
        areas.append(b)
    out["areas"] = areas
    return out


def area_items(prop: dict, area_id: str, limit: int = ITEMS_LISTED) -> List[dict]:
    t = prop.get("titles", {})
    for a in prop.get("areas", []):
        if a["id"] == area_id:
            return [{"name": n, **t.get(n, {"title": n, "kind": "doc"})} for n in a["items"][:limit]]
    return []


# ---------------------------------------------------------------- edits before the yes

class EditError(ValueError):
    pass


def _find(prop: dict, area_id: str) -> dict:
    for a in prop.get("areas", []):
        if a["id"] == area_id:
            return a
    raise EditError(f"no area {area_id}")


def _recount(prop: dict, a: dict) -> None:
    t = prop.get("titles", {})
    a["count"] = len(a["items"])
    a["chats"] = sum(1 for n in a["items"] if t.get(n, {}).get("kind") == "chat")
    a["docs"] = a["count"] - a["chats"]
    a["examples"] = [e for e in a["examples"] if e["name"] in set(a["items"])]
    have = {e["name"] for e in a["examples"]}
    for n in a["items"]:
        if len(a["examples"]) >= EXAMPLES:
            break
        if n not in have:
            a["examples"].append({"name": n, **t.get(n, {"title": n, "kind": "doc"})})


def edit(prop: dict, op: dict) -> dict:
    """rename {area, name}; merge {area, into}; move {item, to}. Returns the proposal with a new id."""
    if prop.get("state") != "proposed":
        raise EditError("the map is not open for edits")
    kind = op.get("op")
    if kind == "rename":
        a = _find(prop, op.get("area"))
        name = _plain(op.get("name"), 40)
        if not name:
            raise EditError("a name is needed")
        if any(o["name"].lower() == name.lower() and o is not a for o in prop["areas"]):
            raise EditError("another area has that name; merge them instead")
        a["name"] = name
        if op.get("line") is not None:
            a["line"] = _plain(op.get("line"), 160)
    elif kind == "merge":
        a, b = _find(prop, op.get("area")), _find(prop, op.get("into"))
        if a is b:
            raise EditError("an area cannot merge into itself")
        b["items"] = b["items"] + [n for n in a["items"] if n not in set(b["items"])]
        prop["areas"] = [o for o in prop["areas"] if o is not a]
        _recount(prop, b)
        if prop.get("_space"):
            prop["_space"]["centroids"].pop(a["id"], None)
    elif kind == "move":
        item, to = op.get("item"), _find(prop, op.get("to"))
        src = next((o for o in prop["areas"] if item in o["items"]), None)
        if src is None:
            raise EditError("no such item in the map")
        if src is to:
            return prop
        src["items"] = [n for n in src["items"] if n != item]
        to["items"] = [item] + to["items"]
        _recount(prop, src); _recount(prop, to)
        if not src["items"]:
            prop["areas"] = [o for o in prop["areas"] if o is not src]
            if prop.get("_space"):
                prop["_space"]["centroids"].pop(src["id"], None)
    else:
        raise EditError("op must be rename, merge or move")
    prop["id"] = proposal_id(prop)
    return prop


# ---------------------------------------------------------------- the store

class PgStore:
    """document_embeddings as the map reads and labels it. `connect` is api.main.get_db_connection."""

    def __init__(self, connect: Callable[[], Any]):
        self.connect = connect

    def items(self, chats: Optional[Dict[str, dict]] = None, only_unlabelled: bool = False, limit: int = 20000,
              names: Optional[List[str]] = None) -> List[dict]:
        from api.chat_continue import is_chat
        conn = self.connect()
        cur = conn.cursor()
        having = "HAVING bool_and(metadata->>'area' IS NULL)" if only_unlabelled else ""
        only = "AND document_name = ANY(%s)" if names else ""
        args = (list(names), limit) if names else (limit,)
        # one vector per document: the mean of its chunks (pgvector's AVG); an older pgvector without it
        # falls back to the first chunk's vector
        rows = None
        for vec_sql in ("AVG(embedding)::text", "(array_agg(embedding::text ORDER BY id ASC))[1]"):
            try:
                cur.execute(f"""
                    SELECT document_name,
                           MAX(metadata->>'title'),
                           substring((array_agg(content ORDER BY id ASC))[1], 1, 600),
                           bool_or(COALESCE(metadata->>'privacy', 'open') <> 'open'),
                           {vec_sql}
                    FROM document_embeddings
                    WHERE metadata->>'deleted_at' IS NULL {only}
                    GROUP BY document_name
                    {having}
                    ORDER BY document_name
                    LIMIT %s
                """, args)
                rows = cur.fetchall()
                break
            except Exception:  # noqa: BLE001
                conn.rollback()
        cur.close(); conn.close()
        rows = rows or []
        out = []
        chats = chats or {}
        for name, title, first, private, vec in rows:
            c = chats.get(name)
            it = {"name": name, "kind": "chat" if (c is not None or is_chat(name)) else "doc", "title": (c or {}).get("title") or title or "",
                  "summary": (c or {}).get("summary") or first or "", "date": ((c or {}).get("last_at") or "")[:10] or None,
                  "private": bool(private), "vec": _parse_vec(vec)}
            out.append(it)
        return out

    def labels(self, names: List[str]) -> Dict[str, Optional[str]]:
        conn = self.connect(); cur = conn.cursor()
        cur.execute("""SELECT document_name, MAX(metadata->>'area') FROM document_embeddings
                       WHERE document_name = ANY(%s) GROUP BY document_name""", (list(names),))
        out = {r[0]: r[1] for r in cur.fetchall()}
        cur.close(); conn.close()
        return out

    def set_labels(self, by_area: Dict[str, List[str]]) -> int:
        conn = self.connect(); cur = conn.cursor()
        n = 0
        for area, names in by_area.items():
            if area is None:
                cur.execute("""UPDATE document_embeddings SET metadata = metadata - 'area'
                               WHERE document_name = ANY(%s)""", (list(names),))
            else:
                cur.execute("""UPDATE document_embeddings SET metadata = COALESCE(metadata, '{}'::jsonb) || jsonb_build_object('area', %s::text)
                               WHERE document_name = ANY(%s)""", (area, list(names)))
            n += cur.rowcount or 0
        conn.commit(); cur.close(); conn.close()
        return n

    def counts(self) -> Dict[str, int]:
        conn = self.connect(); cur = conn.cursor()
        cur.execute("""SELECT COALESCE(area, ''), COUNT(*) FROM (
                         SELECT document_name, MAX(metadata->>'area') AS area FROM document_embeddings
                         WHERE metadata->>'deleted_at' IS NULL GROUP BY document_name) s GROUP BY 1""")
        out = {r[0]: r[1] for r in cur.fetchall()}
        cur.close(); conn.close()
        return out


def _parse_vec(v) -> Optional[List[float]]:
    if v is None:
        return None
    if isinstance(v, (list, tuple)):
        return [float(x) for x in v]
    try:
        return [float(x) for x in str(v).strip("[]() ").split(",") if x.strip()]
    except ValueError:
        return None


# ---------------------------------------------------------------- state on disk

class Maps:
    """The map's files under <runtime>/organise/: proposal.json (open, edited in place), accepted.json (the
    map in force with its feature space, for arrivals), undo.json (the labels before the yes)."""

    def __init__(self, root: Path):
        self.root = Path(root)

    def _p(self, n: str) -> Path:
        return self.root / n

    def read(self, n: str) -> Optional[dict]:
        try:
            return json.loads(self._p(n).read_text(encoding="utf-8"))
        except (FileNotFoundError, ValueError):
            return None

    def write(self, n: str, d: dict) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        f = self._p(n)
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        os.chmod(tmp, 0o600)
        os.replace(tmp, f)

    def drop(self, n: str) -> None:
        try:
            self._p(n).unlink()
        except FileNotFoundError:
            pass

    def state(self) -> dict:
        acc = self.read("accepted.json")
        prop = self.read("proposal.json")
        if prop and prop.get("state") == "proposed":
            return prop
        if acc:
            return acc
        return {"state": "none"}


def label_of(area: dict) -> str:
    """The label a document carries: the area's name as the person left it."""
    return area["name"]


def accept(maps: Maps, store, prop_id: str, world: Optional["World"] = None, now: Optional[float] = None) -> dict:
    prop = maps.read("proposal.json")
    if not prop or prop.get("state") != "proposed":
        raise EditError("no open map")
    if prop_id != prop.get("id"):
        raise EditError(f"the map changed; its id is now {prop.get('id')}")
    names = [n for a in prop["areas"] for n in a["items"]]
    before = store.labels(names)
    by_area = {label_of(a): a["items"] for a in prop["areas"]}
    store.set_labels(by_area)
    t = now or time.time()
    written = world.write(prop) if world else None
    maps.write("undo.json", {"id": prop["id"], "before": before, "world": written,
                             "previous": maps.read("accepted.json")})
    prop["state"] = "accepted"
    prop["accepted"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))
    prop["world"] = f"{world.owner}.world" if written else None   # the name the person sees, not the container path
    maps.write("accepted.json", prop)
    maps.drop("proposal.json")
    return prop


def undo(maps: Maps, store, world: Optional["World"] = None) -> dict:
    u = maps.read("undo.json")
    if not u:
        raise EditError("nothing to undo")
    acc = maps.read("accepted.json") or {}
    back: Dict[Optional[str], List[str]] = defaultdict(list)
    for n, lab in (u.get("before") or {}).items():
        back[lab].append(n)
    # documents labelled on arrival after the yes go back to no label
    known = set(u.get("before") or {})
    for n in acc.get("arrived", []):
        if n not in known:
            back[None].append(n)
    store.set_labels(dict(back))
    removed = world.remove(u.get("world")) if (world and u.get("world")) else 0
    prev = u.get("previous")
    if prev:
        maps.write("accepted.json", prev)
    else:
        maps.drop("accepted.json")
    acc.pop("accepted", None)
    acc["state"] = "proposed"
    acc["id"] = proposal_id(acc)
    acc.pop("arrived", None)
    maps.write("proposal.json", acc)   # the map comes back as a proposal, to edit or to say yes again
    maps.drop("undo.json")
    return {"undone": u.get("id"), "documents": len(u.get("before") or {}), "world_files_removed": removed}


# ---------------------------------------------------------------- arrivals

def assign(acc: dict, item: dict) -> str:
    """The area for a document that arrives after the yes, or `unsorted` (the honest fallback)."""
    sp = acc.get("_space") or {}
    if np is None or not sp.get("centroids"):
        return UNSORTED
    feat = Features.from_json(sp["features"])
    x = feat.matrix([item])[0]
    if not np.any(x):
        return UNSORTED
    best, best_s = None, -1.0
    by_id = {a["id"]: a for a in acc.get("areas", [])}
    for aid, c in sp["centroids"].items():
        a = by_id.get(aid)
        if a is None or a.get("archive"):
            continue
        s = float(x @ np.asarray(c))
        if s > best_s:
            best, best_s = a, s
    if best is None or best_s < ASSIGN_MIN:
        return UNSORTED
    return label_of(best)


def sort_arrivals(maps: Maps, store, chats: Optional[Dict[str, dict]] = None, limit: int = 200,
                  names: Optional[List[str]] = None) -> Dict[str, int]:
    """Label every remembered document that has no area yet (arrived after the yes, through any door);
    `names` limits it to the documents just stored."""
    acc = maps.read("accepted.json")
    if not acc or acc.get("state") != "accepted":
        return {}
    new = store.items(chats=chats, only_unlabelled=True, limit=limit, names=names)
    if not new:
        return {}
    by: Dict[str, List[str]] = defaultdict(list)
    for it in new:
        by[assign(acc, it)].append(it["name"])
    store.set_labels(dict(by))
    acc.setdefault("arrived", []).extend(it["name"] for it in new)
    maps.write("accepted.json", acc)
    return {k: len(v) for k, v in by.items()}


# ---------------------------------------------------------------- <name>.world

def slug(s: str) -> str:
    s = re.sub(r"[^\w\- ]+", "", unicodedata.normalize("NFKC", s), flags=re.UNICODE).strip().lower()
    return re.sub(r"\s+", "-", s)[:48] or "area"


class World:
    """`<name>.world/`: one folder per area with index.md, and a README.md. Files stay where they are; the
    world points to them (the Knowledge page for a document, Continue here for a chat). Only files this
    writer made are ever removed again (by hash)."""

    def __init__(self, root: Path, owner: str, console_url: str = "", today: Optional[str] = None):
        self.root, self.owner, self.url = Path(root), owner, console_url.rstrip("/")
        self.today = today or time.strftime("%Y-%m-%d")

    def _link(self, name: str, kind: str) -> str:
        from urllib.parse import quote
        if not self.url:
            return ""
        if kind == "chat":
            return f"{self.url}/?continue={quote(name)}"
        return f"{self.url}/upload?doc={quote(name)}"

    def _write(self, rel: str, text: str, made: Dict[str, str]) -> None:
        f = self.root / rel
        if f.exists() and rel not in made:
            old = hashlib.sha256(f.read_bytes()).hexdigest()
            if old not in made.values():
                return  # a file the person made: never overwritten
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text, encoding="utf-8")
        made[rel] = hashlib.sha256(text.encode("utf-8")).hexdigest()
        try:   # owned like the world folder (the member's hands), as the laptop import keeps its music
            st = self.root.stat()
            for x in (f, f.parent):
                os.chown(x, st.st_uid, st.st_gid)
            os.chmod(f, 0o644)
        except OSError:
            pass

    def write(self, prop: dict) -> dict:
        made: Dict[str, str] = {}
        t = prop.get("titles", {})
        rows = []
        for a in prop["areas"]:
            d = slug(a["name"])
            lines = [f"# {a['name']}", "", f"Created: {self.today}. Written by the brain from the map you said yes to.", ""]
            if a.get("line"):
                lines += [a["line"], ""]
            lines += [f"{a['count']} items: {a['docs']} documents, {a['chats']} chats.", ""]
            for kind, head in (("doc", "## Documents"), ("chat", "## Chats")):
                names = [n for n in a["items"] if t.get(n, {}).get("kind", "doc") == kind]
                if not names:
                    continue
                lines += [head, ""]
                for n in names:
                    title = t.get(n, {}).get("title") or n
                    link = self._link(n, kind)
                    where = f" ({n})" if kind == "doc" else ""
                    lines.append(f"- [{title}]({link}){where}" if link else f"- {title}{where}")
                lines.append("")
            self._write(f"{d}/index.md", "\n".join(lines), made)
            rows.append(f"- [{a['name']}]({d}/index.md): {a['count']}. {a.get('line', '')}".rstrip())
        head = [f"# {self.owner}.world", "", f"Created: {self.today}. Your map: what the brain found of yours, in the areas you said yes to.",
                "Nothing was moved: every line points to where the thing already is.", ""]
        self._write("README.md", "\n".join(head + rows) + "\n", made)
        return {"root": str(self.root), "files": made}

    def remove(self, written: Optional[dict]) -> int:
        n = 0
        for rel, h in ((written or {}).get("files") or {}).items():
            f = self.root / rel
            try:
                if hashlib.sha256(f.read_bytes()).hexdigest() == h:
                    f.unlink(); n += 1
                    try:
                        f.parent.rmdir() if f.parent != self.root else None
                    except OSError:
                        pass
            except FileNotFoundError:
                pass
        return n


def world_from_env(env=os.environ) -> Optional[World]:
    """The member's world, when they have a hands user: compose mounts ORGANISE_WORLD_HOST_DIR
    (/home/<m>-hands/<m>.world, scripts/member_env.py) at /app/world. Unset: no world is written."""
    host = (env.get("ORGANISE_WORLD_HOST_DIR") or "").strip()
    root = (env.get("ORGANISE_WORLD_DIR") or ("/app/world" if host else "")).strip()
    if not root:
        return None
    owner = Path(host or root).name
    owner = owner[:-6] if owner.endswith(".world") else (env.get("BRAIN_MEMBER") or owner)
    return World(Path(root), owner, env.get("CONSOLE_PUBLIC_URL") or env.get("BRAIN_PUBLIC_URL") or "")
