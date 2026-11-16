"""Moving in, two doors (MOVE-IN-2, 2026-11-16): ui/lib/moveInPlan.js under node. The whole-computer
card's picks, totals, caps and steps; the survey line; the chats list's words; both languages carry
every key. The cards themselves are rendered headless before a push (ops/jobs/briefs/2026-11-16_move-in-2.md)."""
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
    r = subprocess.run([node, "-e", "const m=require('./moveInPlan.js');" + script],
                       capture_output=True, text=True, timeout=30, cwd=str(ROOT / "ui" / "lib"))
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


G = """[{id:'a',files:10,bytes:100,proposal:'knowledge'},{id:'b',files:5,bytes:50,proposal:'files'},
       {id:'c',files:900,bytes:9000,proposal:'leave'}]"""


def test_picks_and_totals():
    out = _node(f"""const g={G}; const p=m.defaultPicks(g); console.log(JSON.stringify([
      p, m.pickTotals(g,p), m.pickTotals(g,{{...p,c:true}}), m.pickTotals(g,{{a:true}}),
      m.overCaps(m.pickTotals(g,{{...p,c:true}}), {{max_files:100,max_bytes:1e9}}), m.overCaps(m.pickTotals(g,p), {{max_files:100,max_bytes:1e9}})]))""")
    assert out[0] == {"a": True, "b": True, "c": False}
    assert out[1] == {"groups": 2, "files": 15, "bytes": 150, "proposed": True}
    assert out[2]["files"] == 915 and out[2]["proposed"] is False
    assert out[3] == {"groups": 1, "files": 10, "bytes": 100, "proposed": False}
    assert out[4] is True and out[5] is False


def test_steps_and_pull():
    out = _node(f"""const g={G}; const open={{survey:true,open:true}}, shut={{survey:true,open:false}}; console.log(JSON.stringify([
      m.surveyStep(null,null,false), m.surveyStep(null,null,true), m.surveyStep(open,{{state:'waiting'}},true),
      m.surveyStep(open,{{state:'plan',groups:g}},false), m.surveyStep(open,{{state:'chosen'}},false),
      m.surveyStep(shut,{{state:'chosen'}},false), m.surveyStep(shut,{{state:'plan'}},false), m.surveyStep({{open:true}},null,false),
      m.pullState({{open:true,arrived:[{{kind:'knowledge'}},{{kind:'media'}},{{kind:'audio'}}]}},{{chosen:['a','b'],groups:g}})]))""")
    assert out[:8] == ["start", "line", "line", "plan", "pulling", "pulled", "start", "start"]
    assert out[8] == {"docs": 1, "kept": 2, "done": 3, "total": 15, "open": True}


def test_survey_line_and_links():
    out = _node("""const c=m.surveyCommands('https://b.example/api/bf','imp_x'); console.log(JSON.stringify([c.mac,c.windows,
      m.continueHref('chatgpt_2025-01-01_a b_1.md','ru'), m.continueHref('claude_x.md','en'), m.fmtBytes(0), m.fmtBytes(1536), m.fmtBytes(5*1024**3),
      m.vendorsOf([{vendor:'ChatGPT'},{vendor:'Claude'},{vendor:'ChatGPT'}])]))""")
    assert out[0] == 'curl -fsSLo brain_import.py "https://b.example/api/bf/documents/import-laptop/helper.py" && python3 brain_import.py --survey --brain "https://b.example/api/bf" --token imp_x'
    assert out[1].startswith("curl.exe ") and "python brain_import.py --survey" in out[1]
    assert out[2] == "/?continue=chatgpt_2025-01-01_a%20b_1.md&lang=ru"
    assert out[3] == "/?continue=claude_x.md"
    assert out[4:7] == ["0 B", "1.5 KB", "5.0 GB"]
    assert out[7] == ["ChatGPT", "Claude"]


def test_both_languages_carry_every_key_and_russian_words():
    out = _node("""const E=m.PLAN_TEXT.en, R=m.PLAN_TEXT.ru; const miss=[];
      for (const k of Object.keys(E)) { if (!(k in R)) miss.push(k); else if (typeof E[k]==='object') for (const j of Object.keys(E[k])) if (!(j in R[k])) miss.push(k+'.'+j) }
      console.log(JSON.stringify([miss, R.listTitle(['ChatGPT','Claude']), E.listTitle(['ChatGPT','Claude']), R.files(21), R.files(3), R.pulled(2,5),
        R.compPlan(7,3221,'4.8 GB'), E.bringProposed(1201,'4.5 GB')]))""")
    assert out[0] == []
    assert out[1] == "Ваши разговоры с ChatGPT и Claude"
    assert out[2] == "Your chats from ChatGPT and Claude"
    assert out[3] == "21 файл" and out[4] == "3 файла"
    assert out[5] == "Пришло: 2 документа ждут вашего «да», 5 файлов сохранено."
    assert out[6] == "Ваш компьютер: 7 групп, 3221 файл, 4.8 GB. Предложение:"
    assert out[7] == "Bring all proposed (1201 files, 4.5 GB)"
