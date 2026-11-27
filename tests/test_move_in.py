"""Moving in on the quiet home (PARENTS-HOME-1 addendum 2, 2026-11-15): the ChatGPT export and the
documents cards come first on a member's home until both are in, each with its state, and the Knowledge
page's import cards speak the console language. ui/lib/moveIn.js and ui/lib/importText.js under node."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _node(script: str):
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")
    r = subprocess.run([node, "-e", "const m=require('./moveIn.js');const t=require('./importText.js');" + script],
                       capture_output=True, text=True, timeout=30, cwd=str(ROOT / "ui" / "lib"))
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_chat_state_steps():
    out = _node(r"""console.log(JSON.stringify([
      m.chatState([], [], null),
      m.chatState([], [], '2026-11-15'),
      m.chatState([{name:'notes.md'}], [{filename:'chatgpt_2025-01-02_x_ab12cd34.md'},{filename:'lecture.pdf'}], '2026-11-15'),
      m.chatState([{name:'chatgpt_2025-01-02_x_1.md', last_updated:'2026-11-14T10:00:00'},{name:'claude_2025-03-01_y_2.md', last_updated:'2026-11-15T09:00:00'},{name:'kto-ya.md'}], [], null),
    ]))""")
    assert [o["step"] for o in out] == ["new", "waiting", "pending", "done"]
    assert out[1]["at"] == "2026-11-15"
    assert out[2]["waitingYes"] == 1           # the pdf is a document, not a conversation
    assert out[3]["n"] == 2 and out[3]["at"].startswith("2026-11-15")


def test_doc_state_and_fold():
    out = _node(r"""const c=m.chatState([{name:'chatgpt_a_1.md',last_updated:'2026-11-15'}],[],null);
      console.log(JSON.stringify([
        m.docState(null, []).step,
        m.docState(null, [{filename:'chatgpt_a.md'}]).step,
        m.docState(null, [{filename:'lecture.pptx'}]).step,
        m.docState({n:3, at:'2026-11-15'}, []).step,
        m.folded(c, m.docState({n:3}, [])),
        m.folded(c, m.docState(null, [])),
      ]))""")
    assert out == ["new", "new", "pending", "done", True, False]


def test_russian_words():
    out = _node(r"""const W=m.moveWords('ru'); console.log(JSON.stringify([
      W.state.chatDone(1, m.day('ru','2026-11-15T10:00')), W.state.chatDone(3, null), W.state.chatDone(48, null),
      W.state.pending(2), W.chatFound(214, 214), W.chatFound(900, 500), m.day('en','2026-01-02'), m.day('ru','junk'),
    ]))""")
    assert out[0] == "перенесён 1 разговор, 15 ноября"
    assert out[1] == "перенесено 3 разговора"
    assert out[2] == "перенесено 48 разговоров"
    assert out[3] == "2 ждут вашего «да»"
    assert out[4] == "Найдено 214 разговоров."
    assert out[5] == "Найдено 900 разговоров, взяты 500 последних."
    assert out[6] == "2 January" and out[7] is None


def test_every_language_has_every_key():
    out = _node(r"""const k=(o)=>Object.keys(o).sort().concat(o.state?Object.keys(o.state).sort():[]);
      console.log(JSON.stringify([k(m.MOVE_TEXT.en), k(m.MOVE_TEXT.ru), k(t.IMPORT_TEXT.en), k(t.IMPORT_TEXT.ru),
        m.MOVE_TEXT.ru.chatSteps.length, m.MOVE_TEXT.en.chatSteps.length, m.HOME_NEWEST]))""")
    assert out[0] == out[1] and out[2] == out[3]
    assert out[4] == out[5] == 3
    assert out[6] == 500


def test_no_english_left_on_the_import_cards():
    up = (ROOT / "ui" / "pages" / "upload.js").read_text()
    lap = (ROOT / "ui" / "lib" / "LaptopImportCard.js").read_text()
    for s in ["Import your ChatGPT or Claude history", "Choose the export zip", "Data controls &gt;"]:
        assert s not in up
    for s in ['"Start"', '"Copy"', "Bring files from your computer</div>", "Keep it to yourself."]:
        assert s not in lap
    assert "useConsoleLang()" in up and 'lang={lang}' in up


def test_home_shows_the_cards_on_the_quiet_home_only_and_reuses_the_doors():
    cc = (ROOT / "ui" / "pages" / "cc.js").read_text()
    # since SWITCH-1 (2026-11-16): not while the first sign-in order shows them as its step 3
    assert "quietHome && !paneMode && !firstStep && (\n            <MoveInCards lang={lang} />" in cc
    # the grey paragraph never shows on the quiet home
    assert "!(quietHome && !paneMode) && (" in cc
    card = (ROOT / "ui" / "components" / "MoveInCards.js").read_text()
    for door in ["/documents/import-chats", "/documents/upload", "/documents/approve-all", "/api/permit"]:
        assert door in card
    # the public template holds no person
    for name in ["Елен", "Александр", "Elena", "Alexander"]:
        assert name not in card and name not in (ROOT / "ui" / "lib" / "moveIn.js").read_text()


def test_start_page_comes_before_moving_in():
    # MEMBER-SCREEN-2 (hbar 2026-11-27): the member's own page is the first screen at every width, the
    # moving-in cards one press away (the page's close); superseded "on a phone moving in stays first"
    cc = (ROOT / "ui" / "pages" / "cc.js").read_text()
    assert "startOpens(d.layout, firstSearch.current)" in cc
    # the quiet pane header: the start page's own name and two words in the console language, no native select
    assert "quiet={quietHome ? {" in cc and "quiet.words.paneClose" in cc
