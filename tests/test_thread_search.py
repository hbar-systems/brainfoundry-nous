"""Thread search regression tests (2026-11-08); no network or live state."""
import ast
import datetime
import sqlite3
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import importlib.util
import sys


def _load(monkeypatch, tmp_path, with_key=False):
    monkeypatch.setenv('HOME', str(tmp_path))
    monkeypatch.setenv('CC_CWD', str(tmp_path / 'brain'))
    monkeypatch.delenv('BRAIN_API_KEY', raising=False)
    spec = importlib.util.spec_from_file_location('cc_bridge_search', ROOT / 'scripts/cc/cc-bridge.py')
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod

ROOT = Path(__file__).resolve().parents[1]


def session_function():
    """Execute the actual endpoint body against an isolated SQL fixture, without booting API services."""
    tree = ast.parse((ROOT / 'api/main.py').read_text())
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'list_chat_sessions')
    fn.decorator_list = []
    namespace = {'Depends': lambda x: None, 'get_api_key': lambda: None,
                 'HTTPException': RuntimeError}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), '<sessions endpoint>', 'exec'), namespace)
    return namespace


def test_actual_session_sql_matches_literal_title_and_content_and_bounds():
    db = sqlite3.connect(':memory:')
    db.create_function('strpos', 2, lambda haystack, needle: (haystack or '').find(needle) + 1)
    db.executescript('''CREATE TABLE chat_sessions(session_id TEXT, model_name TEXT, title TEXT, created_at TEXT, local_only_at TEXT);
        CREATE TABLE chat_messages(id INTEGER, session_id TEXT, content TEXT, created_at TEXT);''')
    for n in range(510):
        db.execute('INSERT INTO chat_sessions VALUES (?, ?, ?, ?, NULL)',
                   (str(n), 'cc', 'title needle' if n == 509 else 'ordinary', f'{n:04}'))
        db.execute('INSERT INTO chat_messages VALUES (?, ?, ?, ?)',
                   (n, str(n), 'content needle' if n in (0, 508) else 'ordinary', f'{n:04}'))
    db.execute("UPDATE chat_messages SET content='100%_literal' WHERE session_id='507'")
    class Cursor:
        def execute(self, sql, params):
            self.rows = db.execute(sql.replace('%s', '?'), params).fetchall()
        def fetchall(self):
            # The real driver returns datetimes; SQLite fixture dates are lexically sorted above.
            return [tuple(row[:3]) + (datetime.datetime(2026, 11, 8),) + tuple(row[4:]) for row in self.rows]
        def close(self): pass
    class Connection:
        def cursor(self): return Cursor()
        def close(self): pass
    namespace = session_function()
    namespace['get_db_connection'] = Connection
    listing = namespace['list_chat_sessions']
    assert {r['session_id'] for r in listing(q='NeEdLe')['sessions']} == {'509', '508'}
    assert [r['session_id'] for r in listing(q='100%_')['sessions']] == ['507']
    assert listing(q='missing')['sessions'] == []
    assert len(listing()['sessions']) == 50
    assert len(listing(q='ordinary')['sessions']) == 200
    # SQL-looking content is a literal parameter, never executable.
    assert listing(q="' OR 1=1 --")['sessions'] == []


def test_bridge_search_archives_registration_and_failure(monkeypatch, tmp_path):
    m = _load(monkeypatch, tmp_path, with_key=False)
    m._threads_save([
        {'brain': 'title', 'title': 'Needle title', 'reasoner': 'codex'},
        {'brain': 'content', 'title': 'a quiet chat'},
        {'brain': 'archived', 'title': 'Needle archive', 'archived': True},
        {'brain': 'other', 'title': 'unrelated'},
    ])
    calls = []
    def api(method, path):
        calls.append((method, path))
        return {'sessions': [{'session_id': 'content'}, {'session_id': 'not-registered'}]}
    monkeypatch.setattr(m, '_brain_api', api)
    monkeypatch.setattr(m.JOBS, 'list', lambda n: [{'id': 'job1', 'thread': 'content', 'title': 'audit', 'ended': 123}])
    monkeypatch.setattr(m.JOBS, 'running_by_thread', lambda: {})
    view = m._threads_view(q='needle')
    rows = {r['brain']: r for r in view['threads']}
    assert set(rows) == {'title', 'content'}
    assert rows['title']['seat'] == 'codex'
    assert rows['content']['seat'] == rows['content']['task_owner'] == 'unknown'
    assert rows['content']['status'] == 'idle'
    assert rows['content']['child_jobs'][0]['id'] == 'job1'
    assert len(calls) == 1 and parse_qs(urlsplit(calls[0][1]).query)['q'] == ['needle']
    assert {r['brain'] for r in m._threads_view(archived=True, q='needle')['threads']} == {'title', 'content', 'archived'}
    monkeypatch.setattr(m, '_brain_api', lambda *args: {'sessions': []})
    assert m._threads_view(q='missing')['threads'] == []
    monkeypatch.setattr(m, '_brain_api', lambda *args: None)
    failed = m._threads_view(q='needle')
    assert failed['search_error'] is True
    assert [r['brain'] for r in failed['threads']] == ['title']
    monkeypatch.setattr(m, '_brain_api', lambda *args: {'error': 'unavailable'})
    assert m._threads_view(q='needle')['search_error'] is True
    monkeypatch.setattr(m, '_brain_api', lambda *args: {'sessions': 'malformed'})
    assert m._threads_view(q='needle')['search_error'] is True


def test_search_is_not_a_new_auth_door():
    bridge = (ROOT / 'scripts/cc/cc-bridge.py').read_text()
    guard = bridge[bridge.index('    def do_GET('):bridge.index('    def do_POST(')]
    # /threads is still handled after the established operator check, unlike /threads/brief.
    assert guard.index('not self._operator_ok()') < guard.index('elif route == "/threads":')
    api = ast.parse((ROOT / 'api/main.py').read_text())
    fn = next(n for n in api.body if isinstance(n, ast.FunctionDef) and n.name == 'list_chat_sessions')
    assert ast.unparse(fn.args.defaults[0]) == 'Depends(get_api_key)'


def test_thread_content_search_refuses_non_operator_before_read(monkeypatch, tmp_path):
    m = _load(monkeypatch, tmp_path)
    replies = []
    class Request:
        def _route(self): return '/threads'
        def _foreign_page(self): return False
        def _operator_ok(self): return False
        def _send(self, status, body): replies.append((status, body))
    monkeypatch.setattr(m, '_threads_view', lambda **kw: (_ for _ in ()).throw(AssertionError('read without operator')))
    m.Handler.do_GET(Request())
    assert replies[0][0] == 403
