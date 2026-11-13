"""IMAP search term (audit 2026-11-13): no CR/LF or control characters reach the SEARCH command."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from api.integrations.email_imap import search_term  # noqa: E402


def test_crlf_and_controls_become_spaces():
    q = search_term('invoice\r\nX1 SELECT INBOX\r\nX2 NOOP\x00\x1b\x7f')
    assert q == "invoice X1 SELECT INBOX X2 NOOP"
    assert not any(ord(c) < 32 or ord(c) == 127 for c in q)


def test_quotes_backslashes_and_non_ascii():
    assert search_term('say "hi" \\ there') == "say hi there"
    assert search_term("café") == ""
    assert search_term("") == "" and search_term(None) == ""
    assert search_term("\r\n\t") == ""
