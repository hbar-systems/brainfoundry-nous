"""
SEC-PASS-1 (2026-11-13): the Odysseus advisory classes checked against nous.
CVE-2026-70619 (non-admin changes a server-wide setting), CVE-2026-70620 (SSRF through a
caller-supplied URL), GHSA-xwhc-f36c-v5vm (non-admin runs OS commands). One test per fix;
no network: DNS and HTTP are stubbed.
"""
import asyncio
import os
import socket
import sys

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from api import apps  # noqa: E402
from api import federation_dm as dm  # noqa: E402
from api import harmonics as h  # noqa: E402
from api import hbar_commands as hc  # noqa: E402
from api.integrations import calendar_ics  # noqa: E402


# ── 1. app install: repo_url / ref can no longer reach git as file://, internal http or an option ──

@pytest.mark.parametrize("url", [
    "file:///app/runtime",
    "http://169.254.169.254/latest/meta-data",
    "https://10.0.0.5/x.git",
    "--upload-pack=touch /tmp/pwned",
    "https://github.com/a/b --upload-pack=x",
    "https://evil.example/a/b",
    "https://github.com/../../etc",
    "ext::sh -c touch% /tmp/pwned",
])
def test_install_request_refuses_non_forge_urls(url):
    with pytest.raises(ValidationError):
        apps.InstallRequest(repo_url=url)


@pytest.mark.parametrize("ref", ["--upload-pack=x", "-b", "a b", "main;id", "a/../b"])
def test_install_request_refuses_option_shaped_refs(ref):
    with pytest.raises(ValidationError):
        apps.InstallRequest(repo_url="https://github.com/hbar-systems/brain-app-clip", ref=ref)


def test_install_request_keeps_forge_urls_and_plain_refs():
    for url in ("https://github.com/hbar-systems/brain-app-clip",
                "https://gitlab.com/a/b.git", "https://codeberg.org/a/b"):
        assert apps.InstallRequest(repo_url=url).repo_url == url
    for ref in ("HEAD", "main", "v1.2.0", "feature/x", "0" * 40):
        assert apps.InstallRequest(repo_url="https://github.com/a/b", ref=ref).ref == ref


def test_git_clone_puts_double_dash_before_positionals(tmp_path, monkeypatch):
    seen = []

    class _Done:
        stdout = "f" * 40

    def fake_run(cmd, **kw):
        seen.append(cmd)
        return _Done()

    monkeypatch.setattr(apps.subprocess, "run", fake_run)
    apps._git_clone("https://github.com/a/b", "main", tmp_path / "dest")
    clone = seen[0]
    assert clone[-3] == "--" and clone[-2] == "https://github.com/a/b"


# ── 2a. calendar ICS: a public feed that redirects inward is refused at the hop ──

class _Resp:
    def __init__(self, status, headers=None, content=b""):
        self.status_code, self.headers, self.content = status, headers or {}, content

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(str(self.status_code))


def _stub_dns(monkeypatch, table):
    def fake(host, *a, **k):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (table[host], 0))]
    monkeypatch.setattr(socket, "getaddrinfo", fake)


def test_calendar_redirect_into_metadata_is_refused(monkeypatch):
    _stub_dns(monkeypatch, {"cal.example": "93.184.216.34", "169.254.169.254": "169.254.169.254"})
    calls = []

    class _Client:
        def __init__(self, *a, **kw):
            assert kw.get("follow_redirects") is False
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def get(self, url, **kw):
            calls.append(url)
            return _Resp(302, {"location": "http://169.254.169.254/latest/meta-data/"})

    monkeypatch.setattr(calendar_ics.httpx, "Client", _Client)
    with pytest.raises(RuntimeError, match="public"):
        calendar_ics._sync_list("https://cal.example/feed.ics", 5)
    assert calls == ["https://cal.example/feed.ics"]


def test_calendar_public_redirect_still_followed(monkeypatch):
    _stub_dns(monkeypatch, {"cal.example": "93.184.216.34", "cdn.example": "93.184.216.35"})
    ics = b"BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n"

    class _Client:
        def __init__(self, *a, **kw): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def get(self, url, **kw):
            if "cal.example" in url:
                return _Resp(301, {"location": "https://cdn.example/feed.ics"})
            return _Resp(200, {}, ics)

    monkeypatch.setattr(calendar_ics.httpx, "Client", _Client)
    assert calendar_ics._sync_list("https://cal.example/feed.ics", 5) == []


# ── 2b. peer handle: one DNS label, so the URL stays on brainfoundry.ai ──

@pytest.mark.parametrize("handle", [
    "169.254.169.254/latest#", "evil.example/?", "a@b", "yury.evil.example", "", "-x", "a b",
])
def test_peer_handle_must_be_one_label(handle):
    with pytest.raises(HTTPException) as e:
        dm.peer_endpoint(handle)
    assert e.value.status_code == 400


def test_peer_handle_ok_and_used_by_both_fetchers(monkeypatch):
    assert dm.peer_endpoint("Yury") == "https://yury.brainfoundry.ai"
    with pytest.raises(HTTPException) as e:
        asyncio.run(dm._fetch_peer_pubkey("127.0.0.1:8000/#"))
    assert e.value.status_code == 400
    with pytest.raises(HTTPException) as e:
        h._fetch_peer("127.0.0.1:8000/#")
    assert e.value.status_code == 400


# ── 2c. peers.introduce / ping: every resolved address, tailnet and IPv6 included ──

@pytest.mark.parametrize("ip", ["100.101.102.103", "10.0.0.1", "::1", "fd00::1", "169.254.169.254"])
def test_peer_url_refuses_non_public_resolution(monkeypatch, ip):
    fam = socket.AF_INET6 if ":" in ip else socket.AF_INET
    monkeypatch.setattr(socket, "getaddrinfo",
                        lambda host, *a, **k: [(socket.AF_INET, 1, 6, "", ("93.184.216.34", 0)),
                                               (fam, 1, 6, "", (ip, 0))])
    with pytest.raises(ValueError, match="private/internal"):
        hc._validate_peer_url("https://peer.example")


def test_peer_url_public_passes(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo",
                        lambda host, *a, **k: [(socket.AF_INET, 1, 6, "", ("93.184.216.34", 0))])
    hc._validate_peer_url("https://peer.example")
