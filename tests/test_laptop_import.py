"""The laptop on-ramp (2026-11-03): scripts/import/brain_import.py and api/laptop_import.py.

Unit tests for the folder rules and the secret skips, the token store, and one end to end:
the helper, run non-interactively over a temp home folder, against the api served by
uvicorn on 127.0.0.1 with NodeOS replaced in-process. No live brain is touched.
"""
import os
import socket
import sys
import tempfile
import threading
import time
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "import"))

if "sentence_transformers" not in sys.modules:
    try:
        import sentence_transformers  # noqa: F401
    except ImportError:
        _st = types.ModuleType("sentence_transformers")
        _st.SentenceTransformer = object
        sys.modules["sentence_transformers"] = _st

os.environ.setdefault("BRAIN_IDENTITY_SECRET", "test-only-secret")
_RUNTIME = tempfile.mkdtemp(prefix="laptop-import-test-")
os.environ.setdefault("BRAIN_RUNTIME_DIR", _RUNTIME)
os.environ.setdefault("SETTINGS_PATH", os.path.join(_RUNTIME, "settings.json"))

import brain_import as h  # noqa: E402
from api import laptop_import as li  # noqa: E402


def _tree(home: Path):
    files = {
        "Documents/plan.md": "# Plan\nmake the record",
        "Documents/notes/day.txt": "a day of notes",
        "Documents/paper.pdf": "%PDF-fake",
        "Documents/photo.jpg": "jpgbytes",
        "Documents/.env": "OPENAI_API_KEY=sk-x",
        "Documents/id_ed25519": "-----BEGIN " "OPENSSH PRIVATE KEY-----",
        "Documents/server.pem": "pem",
        "Documents/vault.kdbx": "kdbx",
        "Documents/my-passwords.txt": "hunter2",
        "Documents/aws_credentials.csv": "AKIA",
        "Documents/node_modules/x/readme.md": "dependency",
        "Documents/.hidden/inside.md": "hidden",
        "Downloads/report.pdf": "%PDF-fake",
        "Downloads/thing.zip": "zip",
        "Downloads/list.csv": "a,b",
        "Music/track.wav": "RIFF",
        "Music/lyrics.txt": "words",
        ".ssh/id_rsa": "key",
        ".aws/credentials": "key",
        "Library/Keychains/login.keychain-db": "kc",
        "myrepo/.git/HEAD": "ref",
        "myrepo/main.py": "print(1)",
        "Projects/a/README.md": "project a",
        "random/thing.md": "not offered",
    }
    for rel, body in files.items():
        p = home / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
    return files


# ── folder rules and secret skips ──────────────────────────────────────

@pytest.mark.parametrize("name", [".ssh", ".gnupg", ".aws", ".password-store", "Library", "AppData",
                                  "node_modules", "Keychains", "1Password", "Photos Library.photoslibrary",
                                  "$Recycle.Bin", "venv"])
def test_skip_dirs(name):
    assert h.skip_dir(name)


@pytest.mark.parametrize("name", ["Documents", "notes", "Projects", "thesis"])
def test_enter_dirs(name):
    assert h.skip_dir(name) == ""


@pytest.mark.parametrize("name", [".env", ".env.local", "prod.env", "id_rsa", "id_ed25519.pub", "server.pem",
                                  "tls.key", "cert.p12", "vault.kdbx", "login.keychain-db", "export.1pux",
                                  "aws_credentials.csv", "my-passwords.txt", "client_secret.json",
                                  "github-token.txt", ".netrc", "backup.gpg"])
def test_skip_secret_files(name):
    assert h.skip_file(name)


@pytest.mark.parametrize("name", ["plan.md", "paper.pdf", "notes.txt", "song.docx", "data.csv"])
def test_offer_plain_files(name):
    assert h.skip_file(name) == ""


def test_candidates_usual_and_projects(tmp_path):
    _tree(tmp_path)
    names = [p.name for p in h.candidates(tmp_path)]
    assert names[:3] == ["Documents", "Downloads", "Music"]
    assert "myrepo" in names and "Projects" in names
    assert "random" not in names and "Library" not in names and ".ssh" not in names


def test_walk_offers_only_readable_non_secret(tmp_path):
    _tree(tmp_path)
    offer = {rel for _p, rel, _s, why in h.walk(tmp_path / "Documents") if not why}
    assert offer == {"plan.md", "notes/day.txt", "paper.pdf", "photo.jpg"}
    s = h.summarize(tmp_path / "Music")
    assert s["offer"] == 1 and s["skipped"] == {"audio (music kit)": 1}


def test_parse_answer():
    assert h.parse_answer("y") == h.DEFAULT_TYPES and "jpg" not in h.parse_answer("y")
    assert h.parse_answer("n") is None and h.parse_answer("") is None
    assert h.parse_answer("pdf, .md") == {"pdf", "md"} == h.parse_answer("t:pdf,md")
    with pytest.raises(ValueError):
        h.parse_answer("wav")


def test_helper_and_brain_agree_on_types():
    assert h.READABLE == li.ACCEPTED_EXT


def test_https_required_except_local():
    with pytest.raises(SystemExit):
        h.Brain("http://me.brainfoundry.ai", "imp_x")
    h.Brain("http://127.0.0.1:9", "imp_x")


def test_dry_run_sends_nothing(tmp_path):
    _tree(tmp_path)
    r = h.run(["--home", str(tmp_path), "--dry-run", "--answers", "documents=y;music=y",
               "--receipt-dir", str(tmp_path)], out=lambda *_: None)
    assert sorted(r["would_send"]) == ["Documents/notes/day.txt", "Documents/paper.pdf", "Documents/plan.md",
                                       "Music/lyrics.txt"]


# ── token store and path cleaning ──────────────────────────────────────

def test_token_one_open_at_a_time_and_hashed(tmp_path):
    st = li.TokenStore(tmp_path / "t.json")
    a = st.mint()["token"]
    b = st.mint()["token"]
    assert a not in (tmp_path / "t.json").read_text()
    with pytest.raises(li.TokenError):
        st.check(a)
    st.check(b)
    st.close(b)
    with pytest.raises(li.TokenError):
        st.check(b)


def test_token_caps_and_expiry(tmp_path):
    st = li.TokenStore(tmp_path / "t.json")
    t = st.mint(max_files=1)["token"]
    st.charge(t, 10)
    with pytest.raises(li.TokenError) as e:
        st.charge(t, 10)
    assert e.value.status == 413
    t2 = st.mint(ttl=-1)["token"]
    with pytest.raises(li.TokenError):
        st.check(t2)


@pytest.mark.parametrize("bad", ["/etc/passwd", "C:/x.txt", "../x.md", "a/../../x.md", "a/.ssh/id", ""])
def test_clean_relpath_refuses(bad):
    with pytest.raises(ValueError):
        li.clean_relpath(bad)


def test_clean_relpath_windows_slashes():
    assert li.clean_relpath("Documents\\notes\\a.md") == "Documents/notes/a.md"


# ── end to end: helper -> local api -> PENDING proposals ───────────────

@pytest.fixture
def server(monkeypatch, tmp_path):
    from api import main as m
    import uvicorn
    seen = types.SimpleNamespace(proposals=[])
    monkeypatch.setattr(m, "PROPOSAL_TEXT_DIR", tmp_path / "proposal_texts")
    (tmp_path / "proposal_texts").mkdir()
    monkeypatch.setattr(m, "_LAPTOP_TOKENS", li.TokenStore(tmp_path / "tokens.json"))
    monkeypatch.setattr(m, "_issue_upload_permit", lambda a, r: {"permit_id": "permit-1", "permit_token": "t"})
    monkeypatch.setattr(m, "extract_text_from_pdf", lambda b: "pdf text " + b.decode())

    def fake_propose(memory_type, content, permit_id, source_refs=None):
        seen.proposals.append({"memory_type": memory_type, "refs": source_refs})
        return {"proposal_id": f"prop-{len(seen.proposals):04d}"}

    def no_decide(*a, **kw):
        raise AssertionError("the import must never decide a proposal")

    monkeypatch.setattr(m, "_nodeos_propose_memory", fake_propose)
    monkeypatch.setattr(m, "_nodeos_decide_memory", no_decide)
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    srv = uvicorn.Server(uvicorn.Config(m.app, host="127.0.0.1", port=port, log_level="warning"))
    th = threading.Thread(target=srv.run, daemon=True)
    th.start()
    for _ in range(100):
        if srv.started:
            break
        time.sleep(0.05)
    seen.url = f"http://127.0.0.1:{port}"
    seen.m = m
    seen.tmp = tmp_path
    yield seen
    srv.should_exit = True
    th.join(5)


def test_end_to_end(server, tmp_path):
    home = tmp_path / "home"
    _tree(home)
    from fastapi.testclient import TestClient
    tok = TestClient(server.m.app).post("/documents/import-laptop/token").json()["token"]
    lines = []
    r = h.run(["--brain", server.url, "--token", tok, "--home", str(home),
               "--answers", "documents=y;downloads=pdf;music=n;myrepo=py",
               "--receipt-dir", str(tmp_path)], out=lines.append)
    sent = sorted(x["path"] for x in r["sent"])
    assert sent == ["Documents/notes/day.txt", "Documents/paper.pdf", "Documents/plan.md",
                    "Downloads/report.pdf", "myrepo/main.py"], (sent, r["refused"])
    assert r["refused"] == [] and r["finished"]["files"] == 5
    names = sorted(p["refs"]["filename"] for p in server.proposals)
    assert names == ["laptop/" + s for s in sent]
    assert all(p["memory_type"] == "document_embedding" for p in server.proposals)
    texts = " ".join(p.read_text() for p in (server.tmp / "proposal_texts").glob("*.txt"))
    assert "make the record" in texts and "pdf text" in texts
    for secret in ("sk-x", "OPENSSH", "hunter2", "AKIA", "kdbx"):
        assert secret not in texts
    assert any("[5/5]" in l for l in lines)
    assert list(tmp_path.glob("brain-import-receipt-*.json"))
    # the token is spent: a second run is refused before anything is listed or sent
    with pytest.raises(SystemExit):
        h.run(["--brain", server.url, "--token", tok, "--home", str(home), "--answers", "documents=y",
               "--receipt-dir", str(tmp_path)], out=lines.append)
    assert len(server.proposals) == 5


def test_route_refuses_without_token_or_with_owner_key(server):
    from fastapi.testclient import TestClient
    c = TestClient(server.m.app)
    files = {"file": ("a.md", b"x", "text/markdown")}
    assert c.post("/documents/import-laptop/file", files=files, data={"path": "a.md"}).status_code == 401
    r = c.post("/documents/import-laptop/file", files=files, data={"path": "a.md"},
               headers={"Authorization": "Bearer " + (server.m.BRAIN_API_KEY or "dev_mode")})
    assert r.status_code == 401
    tok = c.post("/documents/import-laptop/token").json()["token"]
    hdr = {"Authorization": "Bearer " + tok}
    assert c.post("/documents/import-laptop/file", files={"file": ("a.wav", b"RIFF", "audio/wav")},
                  data={"path": "Music/a.wav"}, headers=hdr).status_code == 415
    assert c.post("/documents/import-laptop/file", files=files, data={"path": "../a.md"},
                  headers=hdr).status_code == 400
    assert server.proposals == []
    assert "def run(" in c.get("/documents/import-laptop/helper.py").text
