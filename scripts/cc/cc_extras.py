"""cc_extras: files, jobs and uploads for the CC bridge. Created 2026-09-22.

Imported by cc-bridge.py (same directory). Standard library only.

- Files: list and stream files from a fixed set of roots (the work clones, the mirror,
  the reasoner's out/ and in/ folders, the brain repo). Paths are resolved and must
  stay inside a root; range requests are honoured so audio and video can seek.
- Jobs: commands that outlive a turn. Started detached (own session), logged to
  out/jobs/<id>.log, recorded in out/jobs/jobs.json. Nothing here runs sudo.
- Uploads: multipart bodies from the page, saved under in/<date>/, size-capped.
"""
from __future__ import annotations

import email.parser
import hashlib
import email.policy
import json
import mimetypes
import os
import re
import shlex
import subprocess
import threading
import time
from pathlib import Path

MAX_UPLOAD = 50 * 1024 * 1024
DRAIN_MAX = 256 * 1024 * 1024    # an oversized upload is read away up to this, so the refusal reaches the page
TEXT_SUFFIXES = {".md", ".markdown", ".txt", ".json", ".py", ".js", ".ts", ".sh", ".yml", ".yaml", ".toml", ".csv", ".tsv", ".log", ".css", ".ini", ".cfg"}
KIND_BY_SUFFIX = {
    **{s: "audio" for s in (".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aiff", ".aif")},
    **{s: "video" for s in (".mp4", ".webm", ".mov", ".m4v")},
    **{s: "image" for s in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg")},
    ".pdf": "pdf", ".html": "html", ".htm": "html",
}


class Files:
    def __init__(self, roots: dict[str, str]):
        # label -> absolute path; only existing directories count
        self.roots = {k: Path(v).resolve() for k, v in roots.items() if v and Path(v).is_dir()}

    def resolve(self, raw: str) -> Path | None:
        """A path inside one of the roots, or None. Symlinks are followed before the check."""
        if not raw:
            return None
        try:
            p = Path(raw).expanduser()
            # a relative name ("world-map.html", "ops/x.md") is a path in the world, not in the bridge's cwd
            if not p.is_absolute() and "world" in self.roots:
                p = self.roots["world"] / p
            p = p.resolve()
        except Exception:
            return None
        for root in self.roots.values():
            try:
                p.relative_to(root)
                return p
            except ValueError:
                continue
        return None

    @staticmethod
    def kind(p: Path) -> str:
        s = p.suffix.lower()
        if s in KIND_BY_SUFFIX:
            return KIND_BY_SUFFIX[s]
        if s in TEXT_SUFFIXES or not s:
            return "text"
        return "other"

    # The markdown is the input, a visual is the output (hbar rule 2026-10-09). A note may have a
    # sidecar next to it, `<name>.view.html` (or `<name>.md.view.html`); the Files pane shows it first.
    @staticmethod
    def sidecar(p: Path) -> str | None:
        if p.suffix.lower() not in (".md", ".markdown"):
            return None
        for n in (p.with_suffix("").name + ".view.html", p.name + ".view.html"):
            c = p.with_name(n)
            try:
                if c.is_file():
                    return str(c)
            except OSError:
                pass
        return None

    # ---- finding the file a link means (hbar 2026-10-09: ops/<date>_hackathon-...-brief.md answered
    # 'not a path the reasoner can reach' from a link in an answer). resolve() stays strict (it is the
    # security check); locate() is the forgiving front door: it cleans what a message wraps around a
    # path, then tries every root, then a case-insensitive walk, then a bounded search by name.
    SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", ".next", "dist", "build", ".cache", "site-packages", "target", ".mypy_cache", ".pytest_cache"}
    SEARCH_ENTRIES = 80000
    SEARCH_SECONDS = 2.5

    @staticmethod
    def clean_ref(raw: str) -> str:
        s = (raw or "").strip()
        for _ in range(3):
            before = s
            s = s.strip().strip("`'\"<>").strip()
            if s.lower().startswith("file://"):
                s = s[7:]
            s = re.sub(r"#[^/]*$", "", s) if re.search(r"\.[A-Za-z0-9]{1,6}#[^/]*$", s) else s   # x.md#heading
            s = re.sub(r"(?<=[A-Za-z0-9_\]\)]):\d+(?::\d+)?$", "", s)                         # x.md:12 or :12:3
            s = s.rstrip(".,;:)]}>!?'\"*`")
            if s.startswith("./"):
                s = s[2:]
            if s == before:
                break
        return s

    def _ok(self, p: Path) -> Path | None:
        try:
            q = self.resolve(str(p))
            return q if q is not None and q.exists() else None
        except OSError:
            return None

    @staticmethod
    def _ci_child(base: Path, part: str) -> Path | None:
        c = base / part
        if c.exists():
            return c
        try:
            low = part.lower()
            for e in base.iterdir():
                if e.name.lower() == low:
                    return e
        except OSError:
            pass
        return None

    def _ci_under(self, base: Path, parts: list[str]) -> Path | None:
        cur = base
        for part in parts:
            if part in ("", "."):
                continue
            if part == "..":
                return None
            cur = self._ci_child(cur, part)
            if cur is None:
                return None
        return cur

    def _search(self, rel: str) -> Path | None:
        """A file whose path ends with `rel` (a bare name or a short relative path), found by a
        bounded walk, root by root; within a root the shallowest, then the newest."""
        want = rel.strip("/").lower()
        if not want or ".." in want.split("/"):
            return None
        deadline = time.monotonic() + self.SEARCH_SECONDS
        seen = 0
        order = [k for k in ("world", "work", "in", "out", "brain") if k in self.roots] + [k for k in self.roots if k not in ("world", "work", "in", "out", "brain")]
        for label in order:
            root = self.roots[label]
            best = None
            for dirpath, dirnames, filenames in os.walk(root):
                dirnames[:] = [d for d in dirnames if d not in self.SKIP_DIRS]
                seen += len(filenames) + len(dirnames)
                for fn in filenames:
                    if fn.lower() == want.rsplit("/", 1)[-1]:
                        fp = Path(dirpath) / fn
                        if ("/" + str(fp).lower()).endswith("/" + want):
                            try:
                                key = (len(fp.parts), -fp.stat().st_mtime)
                            except OSError:
                                continue
                            if best is None or key < best[0]:
                                best = (key, fp)
                if seen > self.SEARCH_ENTRIES or time.monotonic() > deadline:
                    break
            if best is not None:
                q = self._ok(best[1])
                if q is not None:
                    return q
            if seen > self.SEARCH_ENTRIES or time.monotonic() > deadline:
                break
        return None

    def locate(self, raw: str) -> Path | None:
        """Where a reference in a message points, or None. Always inside a root."""
        if not raw or not str(raw).strip():
            return None
        for c in dict.fromkeys([raw, self.clean_ref(raw)]):
            if not c:
                continue
            p = self.resolve(c)
            if p is not None and p.exists():
                return p
        c = self.clean_ref(raw)
        if not c:
            return None
        if c.startswith("~"):
            c = os.path.expanduser(c)
        parts = [x for x in c.split("/") if x]
        if c.startswith("/"):
            # a path from another machine ("/Users/hbar/hbar.world/ops/x.md", "/home/cc/world/ops/x.md"):
            # the longest tail that exists under one of our roots
            for i in range(1, len(parts)):
                for root in self.roots.values():
                    q = self._ok(root.joinpath(*parts[i:]))
                    if q is not None:
                        return q
            for i in range(0, len(parts)):
                for root in self.roots.values():
                    q = self._ci_under(root, parts[i:])
                    q = self._ok(q) if q is not None else None
                    if q is not None:
                        return q
            return None
        order = [k for k in ("world", "work", "out", "in", "brain") if k in self.roots]
        for label in order:
            root = self.roots[label]
            q = self._ok(root.joinpath(*parts))
            if q is not None:
                return q
            if parts and parts[0].lower() in (label, root.name.lower(), "hbar.world") and len(parts) > 1:
                q = self._ok(root.joinpath(*parts[1:]))
                if q is not None:
                    return q
        for label in order:
            root = self.roots[label]
            q = self._ci_under(root, parts)
            q = self._ok(q) if q is not None else None
            if q is not None:
                return q
            if parts and parts[0].lower() in (label, root.name.lower(), "hbar.world") and len(parts) > 1:
                q = self._ci_under(root, parts[1:])
                q = self._ok(q) if q is not None else None
                if q is not None:
                    return q
        if not parts:
            return None
        # the page guessed a folder for a bare name and missed: find the file by its name anywhere
        # in the roots (world first, then the desk), with as much of the path as was given
        for tail in (parts, parts[-1:]):
            q = self._search("/".join(tail))
            if q is not None:
                return q
        return None

    def listing(self, raw: str | None) -> dict:
        if not raw:
            return {"path": None, "roots": [{"label": k, "path": str(v)} for k, v in self.roots.items()], "entries": []}
        p = self.locate(raw)
        if p is None or not p.exists():
            return {"error": "not a path the reasoner can reach"}
        if p.is_file():
            st = p.stat()
            d = {"path": str(p), "file": True, "size": st.st_size, "mtime": int(st.st_mtime), "kind": self.kind(p)}
            v = self.sidecar(p)
            if v:
                d["view"] = v
            return d
        entries = []
        try:
            for c in sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
                if c.name.startswith(".") and c.name not in (".hbar",):
                    continue
                try:
                    st = c.stat()
                except OSError:
                    continue
                ent = {"name": c.name, "dir": c.is_dir(), "size": 0 if c.is_dir() else st.st_size,
                       "mtime": int(st.st_mtime), "kind": "dir" if c.is_dir() else self.kind(c)}
                v = None if ent["dir"] else self.sidecar(c)
                if v:
                    ent["view"] = v
                entries.append(ent)
        except PermissionError:
            return {"error": "no permission to read this folder"}
        parent = str(p.parent) if self.resolve(str(p.parent)) else None
        return {"path": str(p), "parent": parent, "entries": entries[:2000],
                "roots": [{"label": k, "path": str(v)} for k, v in self.roots.items()]}

    # Files the person may rewrite from the console (2026-09-28): text inside the world, out or in,
    # never the brain repo, never .env or anything under .git, never a secret. A silent save: the
    # person's own edit of the person's own file needs no permit. Written atomically; group-writable
    # so the hands (a different user after the split) can rewrite what the bridge wrote.
    WRITE_ROOTS = ("world", "out", "in", "work")
    NEVER_NAMES = (".env", ".env.local", ".env.example", "git-credentials", ".netrc")
    WRITE_MAX = 4_000_000

    def writable(self, raw: str) -> tuple[Path | None, str]:
        p = self.resolve(raw)
        if p is None:
            return None, "not a path the reasoner can reach"
        if not any(p == r or r in p.parents for k, r in self.roots.items() if k in self.WRITE_ROOTS):
            return None, "only files in the world, out or in can be edited here"
        parts = p.parts
        if ".git" in parts or any(n in self.NEVER_NAMES or n.endswith(".secret") or n.endswith(".pem") or n.endswith(".key") for n in parts):
            return None, "not editable here: secrets and git internals stay closed"
        if p.exists() and not p.is_file():
            return None, "that is a folder"
        if self.kind(p) != "text":
            return None, "only text files are edited here"
        return p, ""

    def write(self, raw: str, text: str, expect_mtime: int | None = None) -> dict:
        p, why = self.writable(raw)
        if p is None:
            return {"ok": False, "error": why}
        if len(text.encode("utf-8")) > self.WRITE_MAX:
            return {"ok": False, "error": "too large to save from here"}
        if expect_mtime is not None and p.exists() and int(p.stat().st_mtime) != int(expect_mtime):
            return {"ok": False, "error": "changed on disk since you opened it; reload, then edit again", "conflict": True,
                    "mtime": int(p.stat().st_mtime)}
        if not p.parent.is_dir():
            return {"ok": False, "error": "the folder does not exist"}
        tmp = p.parent / f".{p.name}.saving-{os.getpid()}"
        try:
            tmp.write_text(text, encoding="utf-8")
            try:
                os.chmod(tmp, 0o664)
            except OSError:
                pass
            os.replace(tmp, p)
        except OSError as e:
            try:
                tmp.unlink()
            except OSError:
                pass
            return {"ok": False, "error": f"could not save: {e.strerror or e}"}
        st = p.stat()
        return {"ok": True, "path": str(p), "size": st.st_size, "mtime": int(st.st_mtime)}

    def recent(self, root_label: str = "out", n: int = 30) -> list:
        """Newest files under one root (the reasoner's outputs by default), for the pane's
        first view: what was just made, without hunting through folders."""
        root = self.roots.get(root_label)
        if root is None:
            return []
        found = []
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if not d.startswith(".") and d != "jobs"]
            for fn in filenames:
                if fn.startswith("."):
                    continue
                fp = Path(dirpath) / fn
                try:
                    st = fp.stat()
                except OSError:
                    continue
                found.append((st.st_mtime, fp, st.st_size))
        found.sort(key=lambda x: -x[0])
        out = []
        for mt, fp, sz in found[:n]:
            e = {"path": str(fp), "name": fp.name, "dir": str(fp.parent), "size": sz, "mtime": int(mt), "kind": self.kind(fp)}
            v = self.sidecar(fp)
            if v:
                e["view"] = v
            out.append(e)
        return out

    def serve(self, handler, raw: str) -> None:
        """Stream a file with the right type; honour a single byte range."""
        p = self.resolve(raw)
        if p is None or not p.is_file():
            body = b'{"error": "not a file the reasoner can reach"}'
            handler.send_response(404); handler.send_header("Content-Type", "application/json")
            handler.send_header("Content-Length", str(len(body))); handler.end_headers(); handler.wfile.write(body)
            return
        if not os.access(p, os.R_OK):
            # the hands wrote it closed; the post-write hook opens new files, this covers older ones (2026-10-01)
            body = b'{"error": "the reasoner wrote this file closed to the bridge; ask it: open the file to the group (chmod g+r)"}'
            handler.send_response(403); handler.send_header("Content-Type", "application/json")
            handler.send_header("Content-Length", str(len(body))); handler.end_headers(); handler.wfile.write(body)
            return
        size = p.stat().st_size
        ctype = mimetypes.guess_type(p.name)[0] or ("text/plain; charset=utf-8" if self.kind(p) == "text" else "application/octet-stream")
        start, end = 0, size - 1
        rng = handler.headers.get("Range", "")
        m = re.match(r"bytes=(\d*)-(\d*)$", rng.strip())
        partial = False
        if m and size > 0:
            a, b = m.group(1), m.group(2)
            if a:
                start = int(a); end = int(b) if b else size - 1
            elif b:
                start = max(0, size - int(b))
            start = min(start, size - 1); end = min(end, size - 1)
            partial = True
        length = end - start + 1
        handler.send_response(206 if partial else 200)
        handler.send_header("Content-Type", ctype)
        handler.send_header("Accept-Ranges", "bytes")
        handler.send_header("Content-Length", str(length))
        handler.send_header("Cache-Control", "no-store")
        handler.send_header("Content-Disposition", f'inline; filename="{p.name}"')
        if partial:
            handler.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        handler.end_headers()
        try:
            with open(p, "rb") as f:
                f.seek(start)
                left = length
                while left > 0:
                    chunk = f.read(min(1 << 16, left))
                    if not chunk:
                        break
                    handler.wfile.write(chunk)
                    left -= len(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass


class Jobs:
    """Commands that outlive a turn. One registry file; one log per job.

    Each job carries the thread whose hands started it (2026-10-11): cc-job sends CC_THREAD_ID
    and CC_RUN_ID from the reasoner's environment (the bridge sets both when it spawns a turn).
    A thread is only known once its first turn has been recorded, so a job started in a brand new
    conversation arrives with the run id alone; `resolve(run_id)` asks the bridge's run registry
    for the thread later, on finish and on every read. A finished job is handed to its own
    thread's page once (`take_unseen(thread)`); other pages only see it in `unseen_others`,
    never as a tile in their conversation. The board lists every job regardless."""

    UNKNOWN = "unknown"
    UNSEEN_TTL = 24 * 3600      # a finished job nobody took stops being "unseen" after a day

    def __init__(self, out_dir: Path, env_fn, wrap=None, resolve=None, on_end=None, guard=None):
        self.on_end = on_end      # called with the finished record (the spend meter, 2026-10-17)
        # command -> the command to run, or raises with the reason (2026-10-19: a claude started by a
        # job gets the turn's permission hook and may not loosen the owner's posture; cc_guard.check_job)
        self.guard = guard
        self.dir = out_dir / "jobs"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.reg = self.dir / "jobs.json"
        self.env_fn = env_fn
        self.wrap = wrap or (lambda argv: argv)   # runs the job as another user when the bridge says so
        self.resolve = resolve or (lambda run_id: None)   # run id -> thread id, when the bridge knows it by now
        self.lock = threading.Lock()
        self.unseen: set[str] = set()

    @classmethod
    def known(cls, thread) -> bool:
        return bool(thread) and str(thread) != cls.UNKNOWN

    def _load(self) -> list:
        try:
            return json.loads(self.reg.read_text())
        except Exception:
            return []

    def _save(self, items: list) -> None:
        self.reg.write_text(json.dumps(items, indent=1))

    def _fill(self, rec: dict) -> dict:
        """The record with its thread resolved through the run, when it was unknown at start."""
        if not self.known(rec.get("thread")) and rec.get("run"):
            t = None
            try:
                t = self.resolve(rec["run"])
            except Exception:  # noqa: BLE001
                t = None
            if t:
                rec = dict(rec, thread=str(t))
        return rec

    def start(self, command: str, cwd: str | None, title: str = "", thread: str | None = None, run: str | None = None) -> dict:
        command = (command or "").strip()
        if not command:
            return {"error": "empty command"}
        if re.search(r"(^|[\s;&|(])sudo(\s|$)", command):
            return {"error": "jobs never run sudo; ask for that in the chat so it gets a card"}
        run_cmd = command
        if self.guard is not None:
            try:
                run_cmd = self.guard(command)
            except Exception as e:  # noqa: BLE001  (a guard that fails, refuses)
                return {"error": str(e) or type(e).__name__}
        wd = Path(cwd).expanduser() if cwd else None
        if wd is not None and not wd.is_dir():
            return {"error": f"no such folder: {wd}"}
        thread = str(thread or "").strip()[:80] or None
        run = str(run or "").strip()[:40] or None
        if not self.known(thread) and run:
            try:
                thread = str(self.resolve(run) or "") or None
            except Exception:  # noqa: BLE001
                thread = None
        with self.lock:
            items = self._load()
            jid = f"J{int(time.time())}{len(items) + 1:03d}"
            log = self.dir / f"{jid}.log"
            lf = open(log, "ab")
            lf.write(f"# {jid} {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} in {wd or os.getcwd()}\n# {command}\n".encode())
            lf.flush()
            try:
                proc = subprocess.Popen(self.wrap(["bash", "-lc", run_cmd]), cwd=str(wd) if wd else None, env=self.env_fn(),
                                        stdout=lf, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
            except Exception as e:  # noqa: BLE001
                lf.close()
                return {"error": f"could not start: {type(e).__name__}"}
            rec = {"id": jid, "title": (title or command)[:120], "command": command[:1000], "cwd": str(wd) if wd else None,
                   "pid": proc.pid, "started": int(time.time()), "ended": None, "rc": None, "log": str(log),
                   "thread": thread if self.known(thread) else self.UNKNOWN, "run": run}
            items.append(rec)
            self._save(items)

        def _wait():
            rc = proc.wait()
            lf.close()
            done = None
            with self.lock:
                cur = self._load()
                for r in cur:
                    if r["id"] == jid:
                        r["ended"] = int(time.time()); r["rc"] = rc; r.pop("lost", None)
                        # by now the turn that started it has usually recorded its thread
                        r["thread"] = self._fill(r).get("thread") or self.UNKNOWN
                        done = dict(r)
                self._save(cur)
                self.unseen.add(jid)
            if done and self.on_end:
                try:
                    self.on_end(done)
                except Exception:  # noqa: BLE001
                    pass
        threading.Thread(target=_wait, daemon=True).start()
        return rec

    def _reap(self) -> list:
        """The registry with every job whose process is gone marked ended (2026-10-22, issue 9 in
        ops/2026-10-07_brain-use-issues.md): a job whose process died in a bridge restart has no
        `_wait` left to record its end, so it stayed "running" on the board for days and its tile
        could not be closed. On read, a record with no end and a dead pid gets ended=now, rc=None
        and lost=True, written back once. A process of this bridge that just exited is still a
        zombie until `_wait` reaps it, so it reads alive; `_wait` overwrites a lost mark anyway."""
        with self.lock:
            items = self._load()
            now, changed = int(time.time()), False
            for r in items:
                if r.get("ended") is None and not self._alive(r.get("pid"), r.get("started")):
                    r["ended"], r["rc"], r["lost"] = now, None, True
                    changed = True
            if changed:
                try:
                    self._save(items)
                except OSError:
                    pass
        return items

    def list(self, n: int = 30) -> list:
        items = self._reap()
        return [self._fill(r) for r in list(reversed(items))[:n]]

    def running_by_thread(self) -> dict:
        """The jobs still running, grouped by the thread that started them (2026-10-18): the second
        light beside a thread's state, lit while its turn is over and its jobs are not. Only known
        threads; a record whose process is gone (the bridge restarted mid-job) does not count.
        Oldest first within a thread: {thread: [{"id", "title", "started"}]}."""
        out: dict = {}
        for r in self._reap():
            if r.get("ended") is not None:
                continue
            r = self._fill(r)
            th = r.get("thread")
            if not self.known(th) or not self._alive(r.get("pid")):
                continue
            out.setdefault(str(th), []).append({k: r.get(k) for k in ("id", "title", "started")})
        return out

    @staticmethod
    def _alive(pid, started=None) -> bool:
        try:
            os.kill(int(pid), 0)
        except PermissionError:
            pass              # the hands user's process: there, just not ours to signal
        except (ProcessLookupError, TypeError, ValueError):
            return False
        except OSError:
            return True
        # a pid the kernel handed to another process after a restart: it started after the job did
        t0 = Jobs._proc_start(int(pid))
        if started and t0 is not None and t0 > float(started) + 30:
            return False
        return True

    @staticmethod
    def _proc_start(pid: int) -> float | None:
        """When a process started, epoch seconds, from /proc (Linux); None where it cannot be read."""
        try:
            stat = Path(f"/proc/{pid}/stat").read_text()
            ticks = int(stat.rsplit(")", 1)[1].split()[19])      # field 22, starttime
            btime = next(int(ln.split()[1]) for ln in Path("/proc/stat").read_text().splitlines() if ln.startswith("btime "))
            return btime + ticks / os.sysconf("SC_CLK_TCK")
        except Exception:  # noqa: BLE001
            return None

    def get(self, jid: str, tail_bytes: int = 4000) -> dict | None:
        for r in self._reap():
            if r["id"] == jid:
                out = self._fill(dict(r))
                try:
                    data = Path(r["log"]).read_bytes()
                    out["tail"] = data[-tail_bytes:].decode("utf-8", "replace")
                    out["log_size"] = len(data)
                except OSError:
                    out["tail"] = ""
                out["running"] = r["ended"] is None
                return out
        return None

    def _unseen_records(self) -> list:
        """The unseen finished jobs, newest first; ids that are gone or older than UNSEEN_TTL are dropped. Under the lock."""
        now = time.time()
        by_id = {r["id"]: self._fill(r) for r in self._load()}
        keep = []
        for i in list(self.unseen):
            r = by_id.get(i)
            if r is None or (r.get("ended") is not None and now - float(r["ended"]) > self.UNSEEN_TTL):
                self.unseen.discard(i)
                continue
            keep.append(r)
        keep.sort(key=lambda r: float(r.get("ended") or 0), reverse=True)
        return keep

    def take_unseen(self, thread: str | None = None) -> list:
        """Hand over the finished jobs not yet shown. With a thread: only that thread's jobs, so a
        page shows what its own hands started and nothing else. Without one: every unseen job (the
        pre-2026-10-11 behaviour, kept for callers that have no conversation)."""
        with self.lock:
            recs = self._unseen_records()
            if thread is not None:
                recs = [r for r in recs if r.get("thread") == thread]
            for r in recs:
                self.unseen.discard(r["id"])
            ids = [r["id"] for r in recs]
        return [self.get(i, 600) for i in ids]

    def unseen_others(self, thread: str | None) -> list:
        """The finished jobs still unseen that belong to another thread, or to none known. Not
        taken: each page shows them once in a strip, the owning page takes them as tiles."""
        with self.lock:
            recs = [r for r in self._unseen_records() if r.get("thread") != thread or thread is None]
        return [{k: r.get(k) for k in ("id", "title", "ended", "rc", "log", "thread", "started")} for r in recs]

    def mark_seen(self, jid: str) -> bool:
        with self.lock:
            had = jid in self.unseen
            self.unseen.discard(jid)
        return had


def read_body(handler, limit: int) -> bytes | None:
    """A request body, by Content-Length or chunked (2026-10-14). Over the limit it returns None
    after reading the rest away: answering a body we never read made the bridge close a socket
    the proxy was still writing to, and Caddy turned the answer into a bare 502 ("Could not
    attach: 502", 2026-10-09). A body beyond DRAIN_MAX is left unread; the proxy says 502 then."""
    rf = handler.rfile
    if "chunked" in (handler.headers.get("Transfer-Encoding") or "").lower():
        buf, over, seen = bytearray(), False, 0
        while True:
            size = int((rf.readline(1024).split(b";")[0].strip() or b"0"), 16)
            if size == 0:
                while rf.readline(1024) not in (b"\r\n", b"\n", b""):
                    pass                                    # trailers
                return None if over else bytes(buf)
            seen += size
            if seen > DRAIN_MAX:
                return None
            left = size
            while left > 0:
                piece = rf.read(min(left, 1 << 20))
                if not piece:
                    return None
                left -= len(piece)
                if not over:
                    buf += piece
                    if len(buf) > limit:
                        over, buf = True, bytearray()
            rf.readline(1024)                               # the CRLF after each chunk
    n = int(handler.headers.get("Content-Length") or 0)
    if n <= limit:
        return rf.read(n) if n > 0 else b""
    left = n if n <= DRAIN_MAX else 0
    while left > 0:
        piece = rf.read(min(left, 1 << 20))
        if not piece:
            break
        left -= len(piece)
    return None


class RecentSends:
    """One press, one message, on the bridge's side too (2026-10-22, issue 8 in
    ops/2026-10-07_brain-use-issues.md): the same key seen again within `window` seconds is a
    duplicate. `seen(key)` records the key and returns the age of an earlier copy, else None."""

    def __init__(self, window: float = 60.0, clock=time.time):
        self.window, self.clock = window, clock
        self.lock = threading.Lock()
        self.at: dict = {}

    def seen(self, key) -> float | None:
        now = self.clock()
        with self.lock:
            self.at = {k: t for k, t in self.at.items() if now - t < self.window}
            t = self.at.get(key)
            if t is not None:
                return now - t
            self.at[key] = now
            return None

    def forget(self, key) -> None:
        """A copy that was not taken (busy, idle, refused) leaves no mark: the page's own retry of the
        same text through the other door must go through."""
        with self.lock:
            self.at.pop(key, None)


class Uploads:
    def __init__(self, in_dir: Path, window: float = 60.0, clock=time.time):
        self.dir = in_dir
        # (name, size, sha256) -> path: the same file sent again within the window is not saved again;
        # the answer names the copy already on the box, so the message that follows is identical
        # and RecentSends drops it (2026-10-22: New Recording 116-1-2-3-4.m4a)
        self.recent = RecentSends(window, clock)
        self.paths: dict = {}
        self.lock = threading.Lock()   # two presses upload at once: the second waits and finds the first

    @staticmethod
    def _safe_name(name: str) -> str:
        name = os.path.basename(name or "file").strip() or "file"
        name = re.sub(r"[^A-Za-z0-9._ -]+", "_", name)[:120]
        return name

    def save_multipart(self, handler) -> dict:
        ctype = handler.headers.get("Content-Type", "")
        raw = read_body(handler, MAX_UPLOAD)
        if not raw:
            return {"error": f"upload must be between 1 byte and {MAX_UPLOAD // (1024 * 1024)} MB"}
        if not ctype.startswith("multipart/form-data"):
            return {"error": "expected multipart/form-data"}
        msg = email.parser.BytesParser(policy=email.policy.HTTP).parsebytes(
            b"Content-Type: " + ctype.encode() + b"\r\nMIME-Version: 1.0\r\n\r\n" + raw)
        day = time.strftime("%Y-%m-%d", time.gmtime())
        dest_dir = self.dir / day
        try:
            dest_dir.mkdir(parents=True, exist_ok=True)
            if not os.access(dest_dir, os.W_OK):
                raise PermissionError(str(dest_dir))
        except PermissionError:
            # the reasoner made today's folder closed to the bridge (hbar 2026-10-04); say so, do not die
            return {"error": f"today's folder {dest_dir} was made by the reasoner closed to the bridge; ask it: chmod g+w {dest_dir}; the fixups and umask rules prevent this from now on"}
        saved = []
        with self.lock:
            for part in msg.iter_parts():
                fn = part.get_filename()
                if not fn:
                    continue
                data = part.get_payload(decode=True) or b""
                name = self._safe_name(fn)
                fp = (name, len(data), hashlib.sha256(data).hexdigest())
                prev = self.paths.get(fp)
                if self.recent.seen(fp) is not None and prev and Path(prev).is_file() and Path(prev).stat().st_size == len(data):
                    saved.append({"name": Path(prev).name, "path": prev, "size": len(data), "duplicate": True})
                    continue
                dest = dest_dir / name
                i = 1
                while dest.exists():
                    dest = dest_dir / f"{dest.stem}-{i}{dest.suffix}"; i += 1
                try:
                    dest.write_bytes(data)
                except PermissionError:
                    return {"error": f"could not write into {dest_dir}: closed to the bridge"}
                try:
                    os.chmod(dest, 0o664)
                except OSError:
                    pass
                self.paths = {k: v for k, v in self.paths.items() if k in self.recent.at}
                self.paths[fp] = str(dest)
                saved.append({"name": dest.name, "path": str(dest), "size": len(data)})
        if not saved:
            return {"error": "no file in the upload"}
        return {"ok": True, "files": saved}

    def save_bytes(self, name: str, data: bytes) -> str:
        """One file from elsewhere (Telegram, 2026-09-29) into today's folder; returns its path."""
        day = time.strftime("%Y-%m-%d", time.gmtime())
        dest_dir = self.dir / day
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / self._safe_name(name)
        i = 1
        while dest.exists():
            dest = dest_dir / f"{dest.stem}-{i}{dest.suffix}"; i += 1
        dest.write_bytes(data)
        try:
            os.chmod(dest, 0o664)
        except OSError:
            pass
        return str(dest)


def shell_quote(cmd: list[str]) -> str:
    return " ".join(shlex.quote(c) for c in cmd)


class Telegram:
    """The bridge's own bot (2026-09-29): long polling, owner pinning, attachments, cards with
    buttons. Pure parts here, testable with a fake `api`; the bridge wires the turns."""

    LIMIT = 3900

    def __init__(self, token: str, state_file: Path, owner: str = "", api=None):
        self.token = token
        self.state_file = Path(state_file)
        self.forced_owner = str(owner or "").strip()
        self.api = api or self._http
        self._st: dict | None = None

    # -- http --
    def _http(self, method: str, _timeout: int, **params) -> dict:
        import urllib.request
        req = urllib.request.Request(f"https://api.telegram.org/bot{self.token}/{method}",
                                     data=json.dumps(params).encode(), method="POST",
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=_timeout) as r:
            return json.loads(r.read() or b"{}")

    def call(self, method: str, **params) -> dict:
        return self.api(method, 30, **params)

    def poll(self) -> list:
        """One long poll; advances the offset so an update is handled once."""
        st = self.state()
        r = self.api("getUpdates", 40, offset=st.get("offset", 0), timeout=30, allowed_updates=["message", "callback_query"])
        items = r.get("result") or []
        if items:
            self.save(offset=max(u.get("update_id", 0) for u in items) + 1)
        return items

    def download(self, file_id: str, name: str = "") -> tuple[bytes, str]:
        import urllib.request
        info = self.call("getFile", file_id=file_id)
        path = ((info.get("result") or {}).get("file_path") or "")
        if not path:
            raise RuntimeError("no file path")
        with urllib.request.urlopen(f"https://api.telegram.org/file/bot{self.token}/{path}", timeout=120) as r:
            data = r.read()
        return data, (name or Path(path).name)

    # -- state --
    def state(self) -> dict:
        if self._st is None:
            try:
                self._st = json.loads(self.state_file.read_text())
            except Exception:
                self._st = {}
        return self._st

    def save(self, **patch) -> None:
        st = self.state(); st.update(patch)
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(json.dumps(st))

    def owner(self):
        if self.forced_owner:
            try:
                return int(self.forced_owner)
            except ValueError:
                return self.forced_owner
        return self.state().get("owner")

    def owner_ok(self, chat_id) -> bool:
        o = self.owner()
        return o is not None and str(o) == str(chat_id)

    def pin(self, chat_id) -> None:
        self.save(owner=chat_id)

    # -- pure helpers --
    @staticmethod
    def chunks(text: str, n: int = LIMIT) -> list:
        text = text or ""
        out = []
        while len(text) > n:
            cut = text.rfind("\n", 0, n)
            if cut < n // 2:
                cut = text.rfind(" ", 0, n)
            if cut < n // 2:
                cut = n
            out.append(text[:cut]); text = text[cut:].lstrip("\n")
        out.append(text)
        return out

    @staticmethod
    def card_markup(pid: str) -> dict:
        return {"inline_keyboard": [[{"text": "Allow", "callback_data": f"allow:{pid}"},
                                     {"text": "Refuse", "callback_data": f"deny:{pid}"}]]}

    @staticmethod
    def parse_update(u: dict) -> dict | None:
        """What matters in an update: a message (text, voice, photo, document) or a button press."""
        cq = u.get("callback_query")
        if cq:
            msg = cq.get("message") or {}
            return {"kind": "callback", "chat_id": (msg.get("chat") or {}).get("id"), "message_id": msg.get("message_id"),
                    "callback_id": cq.get("id"), "data": cq.get("data") or ""}
        m = u.get("message") or u.get("edited_message")
        if not m:
            return None
        ev = {"kind": "message", "chat_id": (m.get("chat") or {}).get("id"), "message_id": m.get("message_id"),
              "text": (m.get("text") or m.get("caption") or "").strip(), "file_id": None, "file_name": None, "mime": None, "is_voice": False}
        if m.get("voice"):
            v = m["voice"]; ev.update(file_id=v.get("file_id"), file_name="voice.ogg", mime=v.get("mime_type") or "audio/ogg", is_voice=True)
        elif m.get("audio"):
            a = m["audio"]; ev.update(file_id=a.get("file_id"), file_name=a.get("file_name") or "audio.mp3", mime=a.get("mime_type"), is_voice=False)
        elif m.get("photo"):
            best = max(m["photo"], key=lambda p: p.get("file_size") or 0)
            ev.update(file_id=best.get("file_id"), file_name=f"photo-{m.get('message_id')}.jpg", mime="image/jpeg")
        elif m.get("document"):
            d = m["document"]; ev.update(file_id=d.get("file_id"), file_name=d.get("file_name") or "file", mime=d.get("mime_type"))
        elif m.get("video"):
            d = m["video"]; ev.update(file_id=d.get("file_id"), file_name=d.get("file_name") or f"video-{m.get('message_id')}.mp4", mime=d.get("mime_type"))
        return ev


# List prices for the "theoretical" line (2026-10-12): USD per million tokens, per model family:
# fresh input, cache write, cache read, output. Not fetched; a family missing here is priced at the
# default family and marked assumed. The owner can override with CC_PRICES_FILE (same JSON shape).
PRICES_AS_OF = "2026-10-12 (assumed list prices; check the provider's price page)"
PRICES = {"opus": [5.0, 6.25, 0.50, 25.0], "sonnet": [3.0, 3.75, 0.30, 15.0], "haiku": [1.0, 1.25, 0.10, 5.0]}
PRICE_DEFAULT = "opus"


def _price_table() -> tuple:
    f = os.environ.get("CC_PRICES_FILE", "").strip()
    if f:
        try:
            d = json.loads(Path(f).read_text())
            return {k: [float(x) for x in v] for k, v in (d.get("prices") or {}).items()}, str(d.get("as_of") or f)
        except Exception:
            pass
    return PRICES, PRICES_AS_OF


def turn_list_usd(e: dict, table: dict | None = None) -> float:
    """What one turn would cost at list API prices, from its tokens. Older turns did not split fresh
    input from cache writes; their "in" is priced as fresh input (a lower bound)."""
    table = table or PRICES
    m = str(e.get("model") or "").lower()
    fam = next((k for k in table if k in m), PRICE_DEFAULT if PRICE_DEFAULT in table else next(iter(table)))
    p_in, p_cw, p_cr, p_out = table[fam]
    fresh, cw = e.get("tok_fresh"), e.get("tok_cache_write")
    if fresh is None and cw is None:
        fresh, cw = int(e.get("tok_in") or 0), 0
    return (int(fresh or 0) * p_in + int(cw or 0) * p_cw + int(e.get("tok_cached") or 0) * p_cr
            + int(e.get("tok_out") or 0) * p_out) / 1e6


def invoices_read(path) -> list:
    """The owner's invoices for the reasoner (TSV: date provider net_eur gross_eur ref note). Kept in the
    owner's private files, never in this repo; the console only adds them up by period."""
    rows = []
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return rows
    for ln in lines:
        if not ln.strip() or ln.startswith("#") or ln.startswith("date\t"):
            continue
        c = ln.split("\t")
        try:
            rows.append({"date": c[0][:10], "provider": c[1], "net": float(c[2] or 0), "gross": float(c[3] or 0)})
        except (IndexError, ValueError):
            continue
    return rows


def usage_summary(lines, now: float | None = None, titles: dict | None = None, invoices: list | None = None) -> dict:
    """Cost and usage (2026-09-29) from the turn audit: one dict per turn with ts, tok_in, tok_cached,
    tok_out, cost, thread, via, ms. Totals for today, the last 7 days, this month and all time;
    the top threads this month; page against telegram. Cost is a sum where the CLI reported one
    (an API key); on a subscription it stays None and the tokens are the measure."""
    import datetime as _dt
    now = now or time.time()
    today = time.strftime("%Y-%m-%d", time.gmtime(now))
    month = today[:7]
    week_from = time.strftime("%Y-%m-%d", time.gmtime(now - 7 * 86400))
    def blank():
        return {"turns": 0, "in": 0, "cached": 0, "out": 0, "cost": None, "ms": 0, "errors": 0, "list_usd": 0.0}
    def add(b, e):
        b["turns"] += 1
        b["in"] += int(e.get("tok_in") or 0); b["cached"] += int(e.get("tok_cached") or 0); b["out"] += int(e.get("tok_out") or 0)
        b["ms"] += int(e.get("ms") or 0); b["errors"] += 1 if e.get("error") else 0
        b["list_usd"] += turn_list_usd(e, table)
        c = e.get("cost")
        if isinstance(c, (int, float)):
            b["cost"] = (b["cost"] or 0.0) + float(c)
    table, as_of = _price_table()
    out = {"today": blank(), "week": blank(), "month": blank(), "all": blank(), "threads": {}, "via": {}, "days": {}}
    for raw in lines:
        try:
            e = json.loads(raw) if isinstance(raw, str) else raw
        except Exception:
            continue
        day = str(e.get("ts") or "")[:10]
        if not day:
            continue
        add(out["all"], e)
        if day == today:
            add(out["today"], e)
        if day >= week_from:
            add(out["week"], e)
        if day[:7] == month:
            add(out["month"], e)
            th = e.get("brain_session") or e.get("thread") or "?"
            out["threads"].setdefault(th, blank()); add(out["threads"][th], e)
            v = e.get("via") or "page"
            out["via"].setdefault(v, blank()); add(out["via"][v], e)
            out["days"].setdefault(day, blank()); add(out["days"][day], e)
    top = sorted(out["threads"].items(), key=lambda kv: -(kv[1]["in"] + kv[1]["out"]))[:6]
    out["threads"] = [{"thread": k, "title": (titles or {}).get(k), **v} for k, v in top]
    out["days"] = [{"day": k, **v} for k, v in sorted(out["days"].items())][-31:]
    for k in ("today", "week", "month", "all"):
        out[k]["invoiced_net_eur"] = 0.0
        out[k]["invoiced_gross_eur"] = 0.0
    for inv in invoices or []:
        d = inv["date"]
        for k, hit in (("all", True), ("today", d == today), ("week", d >= week_from), ("month", d[:7] == month)):
            if hit:
                out[k]["invoiced_net_eur"] += inv["net"]
                out[k]["invoiced_gross_eur"] += inv["gross"]
    out["prices_as_of"] = as_of
    out["invoices"] = invoices is not None
    out["cost_note"] = ("list USD is computed from tokens at list API prices: what the same work would cost on an "
                        "API key, not a bill. Real money is the invoiced EUR. The reasoner's own cost figure is not "
                        "shown: on resumed threads it reads as a running total and overstates many times over")
    return out


# ---- mission control: one board for all running work (2026-10-06) ----
# Pure assembly from what the bridge already tracks: the run registry (turns in flight and the
# ones just finished, with their events and waiting cards), the turn audit, the threads list,
# the jobs registry and pending permits. No new run system.

BOARD_ORDER = {"waiting": 0, "failed": 1, "answering": 2, "done": 3}


def last_sentence(text: str, n: int = 180) -> str:
    """The last meaningful line of a piece of prose: its final sentence, without markdown noise."""
    s = re.sub(r"```.*?```", " ", text or "", flags=re.S)
    s = re.sub(r"<pane>.*?</pane>", " ", s, flags=re.S)
    s = re.sub(r"\*\*|__|`", "", s)          # emphasis marks are not words
    lines = [l.strip(" #*>-|`") for l in s.splitlines() if l.strip(" #*>-|`")]
    if not lines:
        return ""
    last = lines[-1]
    parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+", last) if p.strip()]
    out = parts[-1] if parts else last
    if len(out) < 24 and len(parts) > 1:
        out = parts[-2] + " " + out
    return out[:n]


def first_sentence(text: str, n: int = 200) -> str:
    """The result line of a finished answer: its opening sentence (an answer leads with its outcome)."""
    s = re.sub(r"```.*?```", " ", text or "", flags=re.S)
    s = re.sub(r"<pane>.*?</pane>", " ", s, flags=re.S)
    s = re.sub(r"\*\*|__|`", "", s)
    lines = [l.strip(" #*>-|`") for l in s.splitlines() if l.strip(" #*>-|`")]
    if not lines:
        return ""
    first = re.split(r"(?<=[.!?])\s+", lines[0])[0].strip()
    return (first or lines[0])[:n]


def links_in(text: str, roots: tuple = (), limit: int = 4) -> list:
    """Links a run produced, read from its answer: web addresses, and files under the given roots."""
    out, seen = [], set()
    for m in re.finditer(r"https?://[^\s)>\]\"'`]+", text or ""):
        u = m.group(0).rstrip(".,;:")
        if u not in seen:
            seen.add(u); out.append({"label": re.sub(r"^https?://", "", u)[:48], "href": u, "kind": "url"})
    for root in [r for r in roots if r]:
        for m in re.finditer(re.escape(root.rstrip("/")) + r"/[^\s)>\]\"'`]+", text or ""):
            fp = m.group(0).rstrip(".,;:")
            if fp not in seen:
                seen.add(fp); out.append({"label": fp.rsplit("/", 1)[-1][:48], "href": "/files?path=" + fp, "kind": "file", "path": fp})
    return out[:limit]


def board_tiles(runs: list, audit_lines, jobs: list, threads: list, pending: list, dismissed: set, now: float,
                result_fn=None, roots: tuple = (), horizon_s: int = 86400) -> dict:
    """One tile per run: every conversation that is answering, waiting on the person, or finished
    in the last 24 h, plus background jobs and permits still waiting. Order: waiting on you,
    failed (pinned until dismissed), answering, done."""
    # a thread's stored title carries the "CC: " mark of the chat record; a tile says the task itself
    titles = {str(th.get("brain")): re.sub(r"^CC:\s*", "", th.get("title") or "untitled") for th in threads if th.get("brain")}
    def iso(ts: float) -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))
    def epoch(s: str) -> float:
        try:
            return __import__("calendar").timegm(time.strptime(str(s)[:19], "%Y-%m-%dT%H:%M:%S"))
        except Exception:
            return 0.0
    def full_id(short: str) -> str | None:
        short = str(short or "")
        if not short:
            return None
        if short in titles:
            return short
        hit = [b for b in titles if b.startswith(short)]
        return hit[0] if len(hit) == 1 else None
    # what the audit knows per thread in the window: totals, the last turn, whether it failed
    per: dict = {}
    for raw in audit_lines:
        try:
            e = json.loads(raw) if isinstance(raw, str) else raw
        except Exception:
            continue
        th = full_id(e.get("brain") or e.get("brain_session"))
        ts = epoch(e.get("ts"))
        if not th or not ts:
            continue
        p = per.setdefault(th, {"turns": 0, "tok": 0, "cost": None, "last_ts": 0.0, "last": None, "fail_ts": 0.0})
        if now - ts <= horizon_s:
            p["turns"] += 1
            p["tok"] += int(e.get("tok_in") or 0) + int(e.get("tok_out") or 0)
            if isinstance(e.get("cost"), (int, float)):
                p["cost"] = (p["cost"] or 0.0) + float(e["cost"])
        if ts >= p["last_ts"]:
            p["last_ts"] = ts; p["last"] = e
    tiles = []
    live_threads = set()
    card_ids = set()
    for r in runs:
        th = r.get("thread")
        cards = r.get("cards") or []
        for c in cards:
            card_ids.add(c.get("id"))
        if r.get("done"):
            continue
        if th:
            live_threads.add(th)
        stats = per.get(th or "", {})
        state = "waiting" if (cards or r.get("waiting")) else "answering"
        tiles.append({"key": f"run:{r.get('run')}", "kind": "run", "run": r.get("run"), "thread": th,
                      "title": titles.get(str(th)) or re.sub(r"^CC:\s*", "", r.get("title") or "") or (r.get("message") or "")[:80] or "new conversation",
                      "state": state, "started": iso(r.get("started") or now), "elapsed_s": int(now - (r.get("started") or now)),
                      "steps": r.get("steps") or 0, "agents": r.get("agents") or 0, "last": r.get("last") or "",
                      "cards": cards, "links": [], "tok": stats.get("tok") or 0, "cost": stats.get("cost"), "turns": stats.get("turns") or 0,
                      "href": f"/talk?thread={th}" if th else None})
    done_runs = {r.get("thread"): r for r in runs if r.get("done") and r.get("thread")}
    # finished conversations: active within the window, or failed and not yet dismissed
    for th_id, title in titles.items():
        if th_id in live_threads:
            continue
        thr = next((x for x in threads if str(x.get("brain")) == th_id), {})
        stats = per.get(th_id, {})
        last_ts = max(epoch(thr.get("last") or thr.get("started")), stats.get("last_ts") or 0.0)
        last = stats.get("last") or {}
        mem = done_runs.get(th_id) or {}
        payload = mem.get("payload") or {}
        failed = bool(payload.get("error")) if payload else bool(last.get("error"))
        stamp = int(last_ts)
        key = f"thread:{th_id}:{stamp}"
        if key in dismissed or thr.get("archived"):
            continue
        if not failed and (not last_ts or now - last_ts > horizon_s):
            continue
        if failed and now - last_ts > 7 * 86400:
            continue
        text = payload.get("reply") or (result_fn(th_id, stamp) if result_fn else "") or ""
        links = links_in(text, roots)
        pane = (payload.get("pane") or {}).get("route") if payload else last.get("pane")
        if pane and not any(l["href"] == pane for l in links):
            links.insert(0, {"label": "opened: " + str(pane).split("?")[0].strip("/"), "href": pane, "kind": "pane"})
        tiles.append({"key": key, "kind": "thread", "run": mem.get("run"), "thread": th_id, "title": title,
                      "state": "failed" if failed else "done", "started": iso(last_ts) if last_ts else None,
                      "elapsed_s": int((payload.get("ms") or last.get("ms") or 0) / 1000), "ago_s": int(now - last_ts) if last_ts else None,
                      "steps": int((payload.get("meta") or {}).get("steps") or 0), "agents": 0,
                      "last": first_sentence(text) or ("stopped by you" if mem.get("stopped") else ""),
                      "cards": [], "links": links[:4], "tok": stats.get("tok") or 0, "cost": stats.get("cost"), "turns": stats.get("turns") or 0,
                      "via": last.get("via"), "href": f"/talk?thread={th_id}"})
    for j in jobs:
        started = float(j.get("started") or 0)
        ended = j.get("ended")
        key = f"job:{j.get('id')}"
        if key in dismissed:
            continue
        failed = ended is not None and ((j.get("rc") or 0) != 0 or bool(j.get("lost")))   # lost: closeable
        if ended is not None and not failed and now - float(ended) > horizon_s:
            continue
        if failed and now - float(ended) > 7 * 86400:
            continue
        tail = [l for l in str(j.get("tail") or "").splitlines() if l.strip() and not l.startswith("# ")]
        th = j.get("thread") if Jobs.known(j.get("thread")) else None
        tiles.append({"key": key, "kind": "job", "run": j.get("id"), "thread": th, "title": j.get("title") or j.get("command") or "job",
                      "state": "answering" if ended is None else ("failed" if failed else "done"), "word": "running" if ended is None else None,
                      "started": iso(started) if started else None, "elapsed_s": int((float(ended) if ended is not None else now) - started) if started else 0,
                      "ago_s": int(now - float(ended)) if ended is not None else None, "steps": 0, "agents": 0,
                      "last": ("its process ended with a bridge restart; no exit code" if j.get("lost") else
                               (tail[-1][:180] if tail else ("exit %s" % j.get("rc") if ended is not None else "started"))),
                      "cards": [], "links": [{"label": "log", "href": "/files?path=" + str(j.get("log") or ""), "kind": "file"}] if j.get("log") else [],
                      "tok": 0, "cost": None, "turns": 0, "href": "/files?path=" + str(j.get("log") or "") if j.get("log") else None})
    for pm in pending:
        if pm.get("id") in card_ids:
            continue
        tiles.append({"key": f"permit:{pm.get('id')}", "kind": "permit", "run": None, "thread": None, "title": pm.get("summary") or "an action waits for your yes",
                      "state": "waiting", "started": pm.get("created_at"), "elapsed_s": 0, "steps": 0, "agents": 0, "last": "proposed earlier, still waiting",
                      "cards": [pm], "links": [], "tok": 0, "cost": None, "turns": 0, "href": None})
    def sort_key(tl):
        recency = -(epoch(tl.get("started")) if tl.get("started") else 0)
        return (BOARD_ORDER.get(tl["state"], 9), recency)
    tiles.sort(key=sort_key)
    counts = {k: sum(1 for tl in tiles if tl["state"] == k) for k in BOARD_ORDER}
    return {"tiles": tiles[:40], "counts": counts, "now": iso(now)}


# ---- Permit history (hbar 2026-10-12: "a place where we can see the historic record of all the permits") ----
# permitd writes one line per event to permitd-audit.jsonl: proposed, approved, denied, executed, failed,
# refused, approve_refused (each with permit_id; proposed/approved/denied carry tool and summarized args).
# The bridge adds permit-decisions.jsonl beside it: who decided (person, standing allow, same turn, judged,
# nobody watching, timeout) and why. History joins the two by permit id. Read-only; never shows secrets.

_SECRET_SHAPED = re.compile(r"(sk-[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9]{20,}|xox[abpr]-[A-Za-z0-9-]{10,}|"
                            r"AKIA[0-9A-Z]{16}|eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}|[A-Fa-f0-9]{40,})")
_FINAL = {"executed": "allowed", "approved": "allowed", "failed": "allowed, failed", "denied": "refused",
          "refused": "refused", "approve_refused": "refused", "proposed": "pending"}


def _scrub(s) -> str:
    return _SECRET_SHAPED.sub("[secret-shaped, hidden]", str(s or ""))


def _jsonl(path) -> list:
    out = []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if isinstance(rec, dict):
                    out.append(rec)
    except OSError:
        pass
    return out


def permit_history(audit_path, decisions_path=None, offset: int = 0, limit: int = 50, thread: str = "",
                   decision: str = "", tool: str = "", q: str = "") -> dict:
    """Every permit, newest first, with what it was, how it ended and who decided. Filters: thread
    (session id prefix), decision (allowed / refused / pending), tool (box method or platform), q (text)."""
    permits: dict = {}
    order: list = []
    loose = []
    for rec in _jsonl(audit_path):
        pid = rec.get("permit_id")
        if not pid:
            # an event with no permit (the gate refused before one existed): keep the reason only
            loose.append({"id": "", "ts": rec.get("ts", ""), "tool": "", "method": "", "platform": "", "summary": "",
                          "decision": "refused", "by": "the gate", "why": _scrub(rec.get("reason") or rec.get("event")),
                          "thread": "", "events": [rec.get("event", "")]})
            continue
        p = permits.get(pid)
        if p is None:
            p = permits[pid] = {"id": pid, "ts": rec.get("ts", ""), "tool": rec.get("tool", ""), "method": "",
                                "platform": "", "summary": "", "decision": "pending", "by": "", "why": "",
                                "thread": "", "events": []}
            order.append(pid)
        args = rec.get("args") or {}
        if isinstance(args, dict) and args:
            p["method"] = p["method"] or str(args.get("method") or "")
            p["platform"] = p["platform"] or str(args.get("platform") or "")
            p["summary"] = p["summary"] or _scrub(args.get("summary") or args.get("action_id") or "")
        ev = rec.get("event", "")
        p["events"].append(ev)
        if ev in _FINAL and ev != "proposed":
            p["decision"] = _FINAL[ev]
            p["decided_at"] = rec.get("ts", "")
        if rec.get("reason") and not p["why"]:
            p["why"] = _scrub(rec.get("reason"))
    for d in _jsonl(decisions_path) if decisions_path else []:
        p = permits.get(d.get("permit_id"))
        if p is None:
            continue
        p["by"] = str(d.get("by") or "")
        p["why"] = _scrub(d.get("why") or p["why"])
        p["thread"] = str(d.get("session") or "")
    rows = [permits[k] for k in order] + loose
    for p in rows:
        if not p["by"]:
            p["by"] = "the gate" if p["decision"] == "refused" and "denied" not in p["events"] else "not recorded"
    rows.sort(key=lambda r: r.get("ts") or "", reverse=True)
    if thread:
        rows = [r for r in rows if r["thread"].startswith(thread)]
    if decision:
        rows = [r for r in rows if r["decision"].startswith(decision)]
    if tool:
        rows = [r for r in rows if tool in (r["method"], r["platform"], r["tool"])]
    if q:
        ql = q.lower()
        rows = [r for r in rows if ql in (r["summary"] + " " + r["why"]).lower()]
    total = len(rows)
    offset = max(0, int(offset or 0))
    limit = max(1, min(200, int(limit or 50)))
    return {"total": total, "offset": offset, "limit": limit, "items": rows[offset:offset + limit]}


# ---- Box map (hbar 2026-10-12: "a map, a diagram of all the spokes and all the parts") ----
# Facts are the owner's file (in the world: ops/box-map/boxes.json); the tailnet adds who is online now.
# Tailnet devices are matched by IP only; a device the facts do not list shows its IP and OS, never its
# host name (a name can carry something private). Read-only.

def box_map(facts: dict, peers: list | None, self_ip: str = "") -> dict:
    boxes = [dict(b) for b in (facts or {}).get("boxes") or [] if isinstance(b, dict) and b.get("id")]
    by_ip = {str(p.get("ip") or ""): p for p in (peers or []) if p.get("ip")}
    known = set()
    for b in boxes:
        ip = str(b.get("tailnet_ip") or "")
        if not ip:
            b["online"] = None                      # not on the tailnet: state unknown from here
        elif ip == self_ip:
            b["online"] = True
            known.add(ip)
        elif peers is None:
            b["online"] = None
        else:
            p = by_ip.get(ip)
            b["online"] = bool(p and p.get("online"))
            known.add(ip)
    for ip, p in sorted(by_ip.items()):
        if ip not in known:
            boxes.append({"id": "unlisted-" + ip, "label": f"unlisted device ({p.get('os') or 'unknown os'})",
                          "ring": 1, "kind": "unlisted", "tailnet_ip": ip, "online": bool(p.get("online")),
                          "runs": [], "users": [], "doors": [], "inside": [],
                          "gaps": ["not in the facts file: add it to ops/box-map/boxes.json"]})
    return {"center": (facts or {}).get("center") or "", "about": (facts or {}).get("about") or "",
            "tailnet": peers is not None, "boxes": boxes}


# ---- Compute view (2026-10-15): which models live on which machine ----
# A box in the facts file may declare its Ollama endpoint(s): "ollama": "http://<host>:11434" (or a list).
# The bridge passes those to the brain api (POST /compute/models), which reads every endpoint live and marks
# each model local or closed with api/privacy.py; this side only assigns endpoints to boxes. Read-only.

def declared_ollama(facts: dict) -> list:
    out = []
    for b in (facts or {}).get("boxes") or []:
        if not isinstance(b, dict) or not b.get("id"):
            continue
        v = b.get("ollama")
        for u in ([v] if isinstance(v, str) else v if isinstance(v, list) else []):
            if isinstance(u, str) and u.strip():
                out.append({"box": str(b["id"]), "url": u.strip()})
    return out


def _url_host(url: str) -> str:
    try:
        from urllib.parse import urlparse
        return (urlparse(url).hostname or "").lower()
    except Exception:
        return ""


def compute_view(facts: dict, res: dict | None) -> dict:
    """Join the api's compute snapshot with the facts: the box's own Ollama goes to the center box, the spoke
    to the box whose tailnet or public IP (or host) is the spoke URL's host. Endpoints the api already tied to
    a declared box keep it. An unanswered api is an empty view with a reason, never an error page."""
    if not isinstance(res, dict) or "endpoints" not in res:
        return {"ok": False, "error": "the brain api did not answer the compute read (is BRAIN_API_KEY in the bridge env?)",
                "endpoints": [], "hosted": [], "summary": {}, "rule": ""}
    boxes = [b for b in (facts or {}).get("boxes") or [] if isinstance(b, dict) and b.get("id")]
    center = (facts or {}).get("center") or next((b["id"] for b in boxes if (b.get("ring") or 0) == 0), "")
    by_addr = {}
    for b in boxes:
        for k in ("tailnet_ip", "public_ip", "host"):
            v = str(b.get(k) or "").strip().lower()
            if v:
                by_addr.setdefault(v, b["id"])
    eps = []
    for e in res.get("endpoints") or []:
        if not isinstance(e, dict):
            continue
        e = dict(e)
        ids = list(e.get("boxes") or [])
        roles = e.get("roles") or []
        if not ids and "box" in roles and center:
            ids.append(center)
        if not ids and "spoke" in roles:
            hit = by_addr.get(_url_host(str(e.get("url") or "")))
            if hit:
                ids.append(hit)
        e["boxes"] = ids
        eps.append(e)
    return {"ok": True, "at": res.get("at"), "cached": bool(res.get("cached")), "rule": res.get("rule") or "",
            "endpoints": eps, "hosted": res.get("hosted") or [], "summary": res.get("summary") or {}}


# ---- Agent shelf (2026-10-15): the ready agent kinds, from the owner's file ----
# The file (in the world: ops/agent-shelf/shelf.json; example in templates/agent-shelf.example.json) is
#   {"about": "...", "legions": [{"id": "...", "name": "..."}], "agents": [{...}, ...]}
# and each agent carries id, name, legion, mission (one line), tools (list), model and/or model_class,
# runs_on (a box id), permit (what always asks) and an optional cost note (free text, the owner's own words).
# A malformed entry is left off the shelf and named in `errors`; the rest still show. Read-only.

SHELF_REL = "ops/agent-shelf/shelf.json"
_SHELF_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_SHELF_TEXT = {"name": 80, "legion": 64, "mission": 200, "model": 120, "model_class": 64, "runs_on": 64,
               "permit": 240, "cost": 240}


def _shelf_agent(a, seen: set):
    if not isinstance(a, dict):
        return None, "not an object"
    aid = a.get("id")
    if not isinstance(aid, str) or not _SHELF_ID.match(aid):
        return None, "id must be a lowercase slug (a-z, 0-9, . _ -), up to 64 characters"
    if aid in seen:
        return None, f"{aid}: duplicate id"
    out = {"id": aid}
    for k, cap in _SHELF_TEXT.items():
        v = a.get(k)
        if v is None:
            continue
        if not isinstance(v, str):
            return None, f"{aid}: {k} must be text"
        v = v.strip()
        if "\n" in v or "\r" in v:
            return None, f"{aid}: {k} must be one line"
        if len(v) > cap:
            return None, f"{aid}: {k} is longer than {cap} characters"
        if v:
            out[k] = v
    for k in ("name", "legion", "mission", "runs_on", "permit"):
        if k not in out:
            return None, f"{aid}: {k} is required"
    if "model" not in out and "model_class" not in out:
        return None, f"{aid}: give a model or a model_class"
    tools = a.get("tools", [])
    if not isinstance(tools, list) or not all(isinstance(t, str) and t.strip() and len(t) <= 80 for t in tools):
        return None, f"{aid}: tools must be a list of short names"
    out["tools"] = [t.strip() for t in tools][:40]
    return out, None


def parse_shelf(obj) -> dict:
    """Validate a shelf document. Returns {"agents", "legions", "errors", "about"}."""
    if not isinstance(obj, dict) or not isinstance(obj.get("agents"), list):
        return {"agents": [], "legions": [], "errors": ["the file must be an object with an \"agents\" list"], "about": ""}
    agents, errors, seen = [], [], set()
    for i, a in enumerate(obj["agents"]):
        got, why = _shelf_agent(a, seen)
        if got is None:
            errors.append(f"entry {i + 1}: {why}")
            continue
        seen.add(got["id"])
        agents.append(got)
    legions, lseen = [], set()
    for l in obj.get("legions") or []:
        if isinstance(l, dict) and isinstance(l.get("id"), str) and l["id"].strip() and l["id"] not in lseen:
            lseen.add(l["id"])
            legions.append({"id": l["id"].strip()[:64], "name": str(l.get("name") or l["id"]).strip()[:80]})
    for a in agents:  # a legion named only on an agent still gets a chip
        if a["legion"] not in lseen:
            lseen.add(a["legion"])
            legions.append({"id": a["legion"], "name": a["legion"]})
    about = obj.get("about") if isinstance(obj.get("about"), str) else ""
    return {"agents": agents, "legions": legions, "errors": errors, "about": about[:400]}


def load_shelf(path) -> dict:
    p = Path(path)
    base = {"path": str(p), "rel": SHELF_REL}
    if not p.is_file():
        return {**base, "exists": False, "agents": [], "legions": [], "errors": [], "about": ""}
    try:
        obj = json.loads(p.read_text())
    except Exception as e:
        return {**base, "exists": True, "agents": [], "legions": [], "about": "",
                "errors": [f"not valid JSON: {type(e).__name__}"]}
    return {**base, "exists": True, **parse_shelf(obj)}
