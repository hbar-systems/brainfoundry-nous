#!/usr/bin/env python3
"""
test_intent_6da.py — Phase 6D-A acceptance test and demo.

Sections:
  1. LLM classification tests  — validate write_commit_push extraction
  2. Plan structure display     — show 9-step plan without execution
  3. Blocked-path demo          — run plan against NodeOS, show governed block

Usage:
    python scripts/test_intent_6da.py              # sections 1 + 2 only
    python scripts/test_intent_6da.py --demo-block # also run section 3 (requires NodeOS)

Environment:
    HBAR_LLM_URL    Ollama base URL   (default: http://localhost:11435)
    HBAR_LLM_MODEL  Ollama model name (default: llama3.2:3b)
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from hbar_shell import (
    Session,
    _llm_intent,
    _validate_intent,
    _validate_write_commit_semantics,
    _print_plan,
    plan_write_commit_push,
    _run_plan,
    _refresh,
    _load_identity,
    _LLM_MODEL,
    _LLM_URL,
)

# ---------------------------------------------------------------------------
# Section 1 — LLM classification tests
# ---------------------------------------------------------------------------

# 3 write_commit_push pass cases, 2 write_commit (no push), 3 unknown
CLASSIFICATION_CASES = [
    # write_commit_push — push keyword present
    {
        "id": "WP1",
        "intent": "create scratch/proof.txt with 'all systems nominal' and push to origin",
        "expected": "write_commit_push",
    },
    {
        "id": "WP2",
        "intent": "write notes/release.txt saying 'v0.17 ready' and deploy it",
        "expected": "write_commit_push",
    },
    {
        "id": "WP3",
        "intent": "save generated/status.txt containing 'Phase 6D-A complete' commit and push",
        "expected": "write_commit_push",
    },
    # write_commit — no push keyword
    {
        "id": "WC1",
        "intent": "create scratch/local.txt saying 'just a note' and commit it",
        "expected": "write_commit",
    },
    {
        "id": "WC2",
        "intent": "write notes/todo.txt with 'fix tests, review PR' and commit",
        "expected": "write_commit",
    },
    # unknown — should refuse
    {
        "id": "U1",
        "intent": "create scratch/a.txt and scratch/b.txt and push both",
        "expected": "unknown",
    },
    {
        "id": "U2",
        "intent": "write /etc/cron.d/hack with 'bad' and push",
        "expected": "unknown",
    },
    {
        "id": "U3",
        "intent": "append a line to scratch/log.txt and push",
        "expected": "unknown",
    },
]


def run_classification(session: Session) -> bool:
    print(f"\n{'─'*68}")
    print(f"Section 1 — LLM classification  (model: {_LLM_MODEL})")
    print(f"{'─'*68}")
    print(f"  {'id':<5}  {'expected':<20}  {'got':<20}  {'ok':<4}  notes")
    print(f"  {'─'*62}")

    results = []
    for case in CLASSIFICATION_CASES:
        sys.stdout.write(f"  {case['id']:<5}  running…\r")
        sys.stdout.flush()

        raw, llm_err = _llm_intent(case["intent"], session, _context="")
        if llm_err:
            got = "error"
            ok = False
            notes = llm_err[:35]
        else:
            data, schema_err = _validate_intent(raw)
            if schema_err:
                got = "schema_error"
                ok = (case["expected"] in ("unknown",))   # schema fail is a safe refusal
                notes = schema_err[:35]
            else:
                got = data["type"]
                ok = (got == case["expected"])
                notes = ""
                # For pass cases: also run semantic validator
                if got in ("write_commit", "write_commit_push") and ok:
                    _, sem_err = _validate_write_commit_semantics(data["params"])
                    if sem_err:
                        ok = False
                        notes = f"sem: {sem_err[:30]}"

        flag = "✓" if ok else "✗"
        print(f"  {case['id']:<5}  {case['expected']:<20}  {got:<20}  {flag}    {notes}")
        results.append(ok)

    passed = sum(results)
    total  = len(results)
    print(f"\n  result: {passed}/{total}")
    all_ok = passed >= total - 1   # allow 1 miss for model variance
    print(f"  {'PASS' if all_ok else 'FAIL'}  (bar: {total-1}/{total})")
    return all_ok


# ---------------------------------------------------------------------------
# Section 2 — Plan structure display (dry run, no NodeOS calls)
# ---------------------------------------------------------------------------

def show_plan_structure(session: Session):
    print(f"\n{'─'*68}")
    print("Section 2 — Plan structure (dry run, no execution)")
    print(f"{'─'*68}")

    path    = "scratch/6da_proof.txt"
    content = "Phase 6D-A complete. Full governed write→commit→preview→push."
    message = "chore: add Phase 6D-A proof file"
    branch  = session.branch or "v0.17-instantiator"

    # Build the same step list as plan_write_commit_push but don't call _confirm
    steps = [
        ("permit request",
         "request permit (fs.write + git.commit + git.preview + git.push, TTL 3600)",
         ["permit", "request", "--agent-id", session.operator_id, "..."]),
        ("propose write",
         f"propose write_file to {path}",
         ["propose", "write", "{permit_id}", "--path", path, "..."]),
        ("approve write",
         f"execute write, create {path}",
         ["proposal", "decide", "{write_proposal_id}", "--approve", "..."]),
        ("propose commit",
         f'propose git_commit: "{message}"',
         ["propose", "commit", "{permit_id}", "--message", message]),
        ("approve commit",
         "execute git commit — hash extracted for push step",
         ["proposal", "decide", "{commit_proposal_id}", "--approve", "..."]),
        ("propose preview",
         "create git_diff_preview — verifies fast-forward before push",
         ["propose", "preview", "{permit_id}"]),
        ("approve preview",
         "execute preview — stops plan if will_fast_forward:False",
         ["proposal", "decide", "{preview_proposal_id}", "--approve", "..."]),
        ("propose push",
         f"create git_push proposal for {branch}",
         ["propose", "push", "{permit_id}", "--branch", branch,
          "--commit-hash", "{commit_hash}", "--preview-snapshot", "{preview_proposal_id}"]),
        ("approve push",
         "execute git push to origin",
         ["proposal", "decide", "{push_proposal_id}", "--approve", "..."]),
    ]

    _print_plan(f'write {path} → commit → preview → push [{branch}]', steps)
    print("  (dry run — no execution)")


# ---------------------------------------------------------------------------
# Section 3 — Blocked-path demo (requires NodeOS at localhost:8001)
# ---------------------------------------------------------------------------

def run_blocked_demo(session: Session):
    print(f"\n{'─'*68}")
    print("Section 3 — Blocked-path demo (live NodeOS execution)")
    print(f"{'─'*68}")
    print("  NodeOS workspace is ahead+1 on a diverged branch.")
    print("  Expect: plan runs through write+commit, preview executes,")
    print("  then either will_fast_forward:False stops the plan, or")
    print("  the push proposal is blocked at 409 by governance.\n")

    ok = _refresh(session)
    if not ok:
        print("  error: could not reach NodeOS — set HBAR_NODEOS_URL")
        return

    print(f"  NodeOS workspace: branch={session.branch} ahead={session.ahead} behind={session.behind}")
    print(f"  operator: {session.operator_id}\n")

    path    = "scratch/6da_block_demo.txt"
    content = "blocked-path demonstration for Phase 6D-A"
    message = "chore: add 6D-A block demo file"

    # Build the 9-step plan exactly as plan_write_commit_push does
    # We call _run_plan directly to avoid the interactive _confirm()
    branch = session.branch
    steps = [
        ("permit request",
         "request permit (fs.write + git.commit + git.preview + git.push, TTL 3600)",
         ["permit", "request",
          "--agent-id", session.operator_id,
          "--loop-type", "governed_git",
          "--scopes", "fs.write,git.commit,git.preview,git.push",
          "--reason", f"6D-A block demo: write {path}, commit, preview, push",
          "--ttl", "3600"]),

        ("propose write",   f"propose write_file to {path}",
         ["propose", "write", "{permit_id}", "--path", path, "--content", content]),

        ("approve write",   f"execute write, create {path}",
         ["proposal", "decide", "{write_proposal_id}",
          "--permit-id", "{permit_id}", "--decided-by", session.operator_id,
          "--approve", "--note", "6da-demo: write"]),

        ("propose commit",  f'propose git_commit: "{message}"',
         ["propose", "commit", "{permit_id}", "--message", message]),

        ("approve commit",  "execute git commit — hash extracted for push step",
         ["proposal", "decide", "{commit_proposal_id}",
          "--permit-id", "{permit_id}", "--decided-by", session.operator_id,
          "--approve", "--note", "6da-demo: commit"]),

        ("propose preview", "create git_diff_preview proposal",
         ["propose", "preview", "{permit_id}"]),

        ("approve preview", "execute preview — stops if will_fast_forward:False",
         ["proposal", "decide", "{preview_proposal_id}",
          "--permit-id", "{permit_id}", "--decided-by", session.operator_id,
          "--approve", "--note", "6da-demo: preview"]),

        ("propose push",    f"create git_push proposal for {branch}",
         ["propose", "push", "{permit_id}",
          "--branch", branch,
          "--commit-hash", "{commit_hash}",
          "--preview-snapshot", "{preview_proposal_id}"]),

        ("approve push",    "execute git push to origin",
         ["proposal", "decide", "{push_proposal_id}",
          "--permit-id", "{permit_id}", "--decided-by", session.operator_id,
          "--approve", "--note", "6da-demo: push"]),
    ]

    print("  Running plan (no confirmation prompt in test mode)…")
    result = _run_plan(steps, session)
    print()
    if result:
        print("  plan completed — push succeeded (workspace was fast-forwardable)")
    else:
        print("  plan stopped — governed block confirmed")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    demo_block = "--demo-block" in sys.argv

    session = Session()
    session.operator_id = _load_identity()
    session.branch = "v0.17-instantiator"
    session.head   = "unknown"
    session.ahead  = 0
    session.behind = 0

    ok1 = run_classification(session)
    show_plan_structure(session)

    if demo_block:
        run_blocked_demo(session)
    else:
        print(f"\n  (pass --demo-block to run Section 3 against live NodeOS)\n")

    sys.exit(0 if ok1 else 1)


if __name__ == "__main__":
    main()
