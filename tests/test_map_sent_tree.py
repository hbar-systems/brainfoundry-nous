# MAP-AGENTS-1 (hbar 2026-11-24): /map shows the structure of the agents that are sent.
from pathlib import Path

SRC = (Path(__file__).resolve().parents[1] / "ui" / "pages" / "map.js").read_text()


def test_map_draws_the_sent_tree():
    assert "export function buildTree(" in SRC
    assert "<Tree tree={tree}" in SRC and "useState(true)" in SRC
    # each node carries the subagent count, the jobs with their state, time and last line
    assert "Number(l.head.agents)" in SRC and "s.last" in SRC and "n.head.last" in SRC


def test_map_reads_only_what_the_board_serves():
    # the tree adds no new fetch: same /cc/board, /cc/actions, /api/bf/tasks
    assert SRC.count("fetch('") == 3
