"""Language settings (hbar 2026-10-25): the two prompt lines
(api/language_prefs.prompt_lines) and the settings round trip
(api/settings_store.get_language / set_language). No network.

Run from repo root:
    pytest tests/test_language.py -v
"""
import pytest

from api import language_prefs as lp


def test_defaults_produce_no_lines():
    assert lp.prompt_lines("auto", "off", 50) == ""
    assert lp.prompt_lines_from({}) == ""
    assert lp.prompt_lines_from({"answer": "auto", "learning": "off", "balance": 50}) == ""


def test_answer_ru_learning_off_is_one_line():
    out = lp.prompt_lines("ru", "off", 50)
    assert out.count("\n") == 0
    assert out.startswith("Language: answer in Russian (ru)")
    assert "wins over any language instruction in the persona" in out


def test_en_learning_de_at_50_and_100():
    half = lp.prompt_lines("en", "de", 50)
    l1, l2 = half.split("\n")
    assert l1 == "Language: the person's own language is English (en)."
    assert l2.startswith("Learning: the person is learning German (de).")
    assert "about 50% of the answer in German (de) and the rest in English (en)" in l2
    assert "under a thin rule (---), give the same answer entirely in English (en)" in l2
    full = lp.prompt_lines("en", "de", 100)
    assert "Write the whole answer in German (de)" in full.split("\n")[1]
    assert "about" not in full.split("\n")[1].split(";")[0]
    low = lp.prompt_lines("en", "de", 0)
    assert "only a sentence or two of the answer in German (de)" in low


def test_auto_with_learning_names_the_language_written_in():
    out = lp.prompt_lines("auto", "ru", 50)
    assert "own language is the language the person writes in" in out
    assert "entirely in the language the person writes in" in out


def test_other_free_text_and_bad_balance():
    out = lp.prompt_lines("Portuguese", "Japanese", "x")
    assert "own language is Portuguese." in out
    assert "learning Japanese." in out
    assert "about 50%" in out            # bad balance falls back to the default
    assert "about 100%" not in lp.prompt_lines("en", "de", 250)   # clamped to 100


def test_settings_round_trip(monkeypatch, tmp_path):
    monkeypatch.setattr("api.settings_store.SETTINGS_PATH", tmp_path / "settings.json")
    monkeypatch.setenv("BRAIN_IDENTITY_SECRET", "test-secret-language")
    from api import settings_store as s
    assert s.get_language() == {"answer": "auto", "learning": "off", "balance": 50}
    s.set_language(answer="en", learning="de")
    assert s.get_language() == {"answer": "en", "learning": "de", "balance": 50}
    s.set_language(balance=100)
    assert s.get_language()["balance"] == 100
    s.set_language(balance=-5)
    assert s.get_language()["balance"] == 0
    s.set_language(answer="  ", learning="  Japanese  ")          # blank resets to the default
    assert s.get_language()["answer"] == "auto"
    assert s.get_language()["learning"] == "Japanese"
    with pytest.raises(ValueError):
        s.set_language(balance="50")
    assert lp.prompt_lines_from(s.get_language()).startswith("Language: the person's own language is the language the person writes in.")
