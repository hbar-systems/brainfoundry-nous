import time
import requests
import uuid
import json
from typing import Any, Dict, List, Optional


NODEOS = "http://127.0.0.1:8001"

PERMIT_ID = None


NODEOS_BASE = "http://127.0.0.1:8001"

BACKOFF_INITIAL = 1.0
BACKOFF_MAX = 20.0
BACKOFF_MULT = 1.5
IDLE_SLEEP = 3.0


def nodeos_get(url: str) -> Any:
    r = requests.get(url, timeout=10)
    r.raise_for_status()
    if not r.text.strip():
        return None
    return r.json()


def nodeos_list_pending(limit: int = 10) -> List[Dict[str, Any]]:
    url = f"{NODEOS_BASE}/v1/actions?status=PENDING&limit={limit}"
    data = nodeos_get(url)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return data.get("items") or data.get("actions") or []
    return []


def nodeos_get_action(proposal_id: str) -> Dict[str, Any]:
    url = f"{NODEOS_BASE}/v1/actions/{proposal_id}"
    data = nodeos_get(url)
    return data if isinstance(data, dict) else {}


def nodeos_get_commit_result(proposal_id: str) -> Dict[str, Any]:
    url = f"{NODEOS_BASE}/v1/actions/{proposal_id}/commit"
    data = nodeos_get(url)
    return data if isinstance(data, dict) else {}


def extract_status(action_obj: Dict[str, Any]) -> str:
    v = action_obj.get("status") or action_obj.get("state") or "UNKNOWN"
    return str(v).upper()


def summarize_commit_result(commit_obj: Dict[str, Any]) -> str:
    ok = commit_obj.get("ok")

    # /v1/actions/{id}/commit returns {"ok": true, "commit": {...}}
    commit = commit_obj.get("commit")
    if isinstance(commit, dict):
        result = commit.get("result")
    else:
        result = commit_obj.get("result")

    if not isinstance(result, dict):
        result = {}


    branch = result.get("branch") or "?"
    ahead = result.get("ahead")
    behind = result.get("behind")
    local_head = result.get("local_head") or "?"
    remote_head = result.get("remote_head") or "?"
    diff_stat = (result.get("diff_stat") or "").strip()
    diff = (result.get("diff") or "").strip()

    def fmt_int(x: Any) -> str:
        try:
            return str(int(x))
        except Exception:
            return "?"

    out = []
    out.append(f"commit-result ok={ok} branch={branch} ahead={fmt_int(ahead)} behind={fmt_int(behind)}")
    out.append(f"  local_head={local_head}")
    out.append(f"  remote_head={remote_head}")
    out.append("  diff_stat: " + (diff_stat if diff_stat else "(empty)"))
    out.append("  diff: " + ("(empty)" if not diff else "(see below)"))
    if diff:
        out.append(diff)
    return "\n".join(out)





def request_permit():
    global PERMIT_ID

    payload = {
        "node_id": "brainloop",
        "agent_id": "brainloop-agent",
        "loop_type": "admin",
        "ttl_seconds": 3600,
        "scopes": ["git.preview"],
        "reason": "brainloop-test"
    }

    r = requests.post(f"{NODEOS}/v1/loops/request", json=payload)
    r.raise_for_status()

    data = r.json()
    PERMIT_ID = data["permit_id"]

    print("Permit:", PERMIT_ID)


def pending_actions():
    r = requests.get(f"{NODEOS}/v1/actions?status=PENDING&limit=1")
    r.raise_for_status()
    data = r.json()

    # NodeOS returns: {"ok":true, "count":N, "proposals":[...]}
    proposals = []
    if isinstance(data, dict):
        proposals = data.get("proposals") or []
    if not isinstance(proposals, list):
        proposals = []

    return proposals


def propose_preview():
    payload = {
        "permit_id": PERMIT_ID,
        "action_type": "git_diff_preview",
        "payload": {
            "repo": ".",
            "max_bytes": 20000
        }
    }

    r = requests.post(f"{NODEOS}/v1/actions/propose", json=payload)
    r.raise_for_status()

    print("Proposed preview:", r.json()["proposal_id"])


def main():

    request_permit()

    last_proposal_id = None
    backoff = BACKOFF_INITIAL

    while True:

        try:

            # Sticky latch: if we are already waiting on a proposal, keep waiting on it
            # regardless of what the global pending list says.
            if last_proposal_id is None:
                pending = pending_actions()

                if len(pending) == 0:
                    # nothing pending -> propose
                    backoff = BACKOFF_INITIAL
                    print("No pending actions → proposing preview")
                    propose_preview()
                    time.sleep(5)
                    continue

                pid = pending[0].get("proposal_id") or pending[0].get("id")
                last_proposal_id = str(pid)
                backoff = BACKOFF_INITIAL
                print(f"[brainloop] found pending {last_proposal_id}; waiting")

            # from here on: we have a latched proposal id and we poll it until terminal

            # Use the status directly from the pending list item (authoritative + not nested)
            # Poll the proposal itself so we can observe terminal states after it leaves the pending list
            action = nodeos_get_action(last_proposal_id)
            prop = action.get("proposal") if isinstance(action, dict) else None
            if isinstance(prop, dict):
                status = str(prop.get("status") or "UNKNOWN").upper()
            else:
                status = "UNKNOWN"

            if status == "PENDING":
                print(f"[brainloop] waiting on {last_proposal_id} status=PENDING (sleep {backoff:.1f}s)")
                time.sleep(backoff)
                backoff = min(BACKOFF_MAX, backoff * BACKOFF_MULT)
                continue

            print(f"[brainloop] proposal {last_proposal_id} status={status}")


            # If it isn't PENDING, we’ll fetch the full proposal for context (optional)
            action = nodeos_get_action(last_proposal_id)
            print(f"[brainloop] proposal {last_proposal_id} status={status}")



            # terminal state
            if status == "APPROVED":
                try:
                    commit_obj = nodeos_get_commit_result(last_proposal_id)
                    if commit_obj:
                        print(summarize_commit_result(commit_obj))

                        # If the preview shows no changes, don't spam new previews.
                        c = commit_obj.get("commit") if isinstance(commit_obj, dict) else None
                        r = c.get("result") if isinstance(c, dict) else None
                        if isinstance(r, dict):
                            diff = (r.get("diff") or "").strip()
                            diff_stat = (r.get("diff_stat") or "").strip()
                            if not diff and not diff_stat:
                                print("[brainloop] preview is empty → idling (no new proposals)")
                                last_proposal_id = None
                                backoff = BACKOFF_INITIAL
                                time.sleep(60)
                                continue
                    else:
                        print("[brainloop] commit-result: (none)")
                except Exception as e:
                    print(f"[brainloop] commit-result fetch failed: {e}")
            else:
                print("[brainloop] not approved; skipping commit-result fetch")





            # clear latch so next loop can propose again when pending is empty
            last_proposal_id = None
            backoff = BACKOFF_INITIAL
            time.sleep(IDLE_SLEEP)

        except Exception as e:
            print("Loop error:", e)
            time.sleep(2)




if __name__ == "__main__":
    main()
