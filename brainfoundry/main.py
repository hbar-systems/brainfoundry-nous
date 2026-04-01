from fastapi import FastAPI, Header, HTTPException

from pydantic import BaseModel
import re

import os, json, urllib.request, subprocess
from pathlib import Path

import shutil

import contextlib
app = FastAPI(title="BrainFoundry", version="0.1.0")

OPERATOR_TOKEN = os.getenv("BRAINFOUNDRY_OPERATOR_TOKEN", "dev-operator-token")

AUDIT_PATH = os.getenv(
    "BRAINFOUNDRY_AUDIT_PATH",
    str(Path(__file__).with_name("audit.jsonl")),
)

def audit_log(
    action: str,
    brain_id: str | None = None,
    ok: bool = True,
    detail: dict | None = None,
    error: str | None = None,
):
    """
    Append-only audit log (jsonl). Never blocks API on audit failures.
    """
    try:
        from datetime import datetime, timezone

        event = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "service": "brainfoundry",
            "action": action,
            "brain_id": brain_id,
            "ok": ok,
            "detail": detail or {},
        }
        if error:
            event["error"] = error

        p = Path(AUDIT_PATH)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, sort_keys=True) + "\n")
            f.flush()
    except Exception:
        # do not break API if audit logging fails
        return




REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
COMPOSE_FILE = REPO_ROOT / "docker-compose.instantiator.yml"


def lifecycle_available() -> tuple[bool, str]:
    # Host-run lifecycle requires docker CLI + a working daemon.
    try:
        if shutil.which("docker") is None:
            return False, "docker CLI not found"
        r = subprocess.run(["docker", "info"], capture_output=True, text=True)
        if r.returncode != 0:
            msg = ((r.stdout or "") + (r.stderr or "")).strip()
            return False, msg or "docker unavailable"
        return True, "ok"
    except Exception as e:
        return False, str(e)

def require_lifecycle() -> None:
    ok, reason = lifecycle_available()
    if not ok:
        raise HTTPException(status_code=503, detail=f"lifecycle disabled: {reason}")



_LIFECYCLE_LOCKS: dict[str, object] = {}
_LIFECYCLE_LOCKS_GUARD = None

def _lock_for(brain_id: str):
    global _LIFECYCLE_LOCKS_GUARD
    if _LIFECYCLE_LOCKS_GUARD is None:
        import threading
        _LIFECYCLE_LOCKS_GUARD = threading.Lock()
    with _LIFECYCLE_LOCKS_GUARD:
        lock = _LIFECYCLE_LOCKS.get(brain_id)
        if lock is None:
            import threading
            lock = threading.Lock()
            _LIFECYCLE_LOCKS[brain_id] = lock
        return lock

@contextlib.contextmanager
def lifecycle_lock(brain_id: str):
    lock = _lock_for(brain_id)
    acquired = lock.acquire(blocking=False)
    if not acquired:
        raise HTTPException(status_code=409, detail="lifecycle busy")
    try:
        yield
    finally:
        lock.release()

def registry_path() -> Path:
    # file lives inside the image at /app/brainfoundry/registry.json
    return Path(__file__).with_name("registry.json")

def read_registry_doc() -> dict:
    p = registry_path()
    doc = json.loads(p.read_text(encoding="utf-8"))
    return validate_registry_doc(doc)


def validate_registry_doc(doc: dict) -> dict:
    """
    Validate and normalize registry document.
    Enforces:
      - doc is {"brains": [...]} (brains optional)
      - each brain has brain_id (str), service (str), port (int)
      - uniqueness: brain_id, service, port
    Returns normalized doc with deterministic sorting by port.
    """
    if not isinstance(doc, dict):
        raise ValueError("registry doc must be an object")

    brains = doc.get("brains", [])
    if brains is None:
        brains = []
    if not isinstance(brains, list):
        raise ValueError("registry.brains must be a list")

    norm: list[dict] = []
    seen_brain_id: set[str] = set()
    seen_service: set[str] = set()
    seen_port: set[int] = set()

    for i, b in enumerate(brains):
        if not isinstance(b, dict):
            raise ValueError(f"registry.brains[{i}] must be an object")

        brain_id = (b.get("brain_id") or "").strip()
        service = (b.get("service") or "").strip()

        if brain_id == "" or service == "":
            raise ValueError(f"registry.brains[{i}] missing brain_id/service")

        try:
            port = int(b.get("port"))
        except Exception:
            raise ValueError(f"registry.brains[{i}].port must be int")

        if brain_id in seen_brain_id:
            raise ValueError(f"duplicate brain_id: {brain_id}")
        if service in seen_service:
            raise ValueError(f"duplicate service: {service}")
        if port in seen_port:
            raise ValueError(f"duplicate port: {port}")

        seen_brain_id.add(brain_id)
        seen_service.add(service)
        seen_port.add(port)

        norm.append({"brain_id": brain_id, "service": service, "port": port})

    norm_sorted = sorted(norm, key=lambda x: int(x["port"]))
    return {"brains": norm_sorted}


def write_registry_doc(doc: dict) -> None:
    """
    Atomic write: write temp file then replace.
    Deterministic formatting + validation.
    """
    p = registry_path()
    p.parent.mkdir(parents=True, exist_ok=True)

    normalized = validate_registry_doc(doc)
    payload = json.dumps(normalized, indent=2, sort_keys=True) + "\n"

    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    os.replace(str(tmp), str(p))


def service_name_for(brain_id: str) -> str:
    last = brain_id.split(".")[-1]
    safe = re.sub(r"[^a-zA-Z0-9_]", "_", last)
    return f"api_{safe}"


def docker_compose(*args: str) -> None:
    # allowlisted: docker compose -f docker-compose.instantiator.yml <args...>
    r = subprocess.run(
        ["docker", "compose", "-f", str(COMPOSE_FILE), *args],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        msg = ((r.stdout or "") + (r.stderr or "")).strip()
        raise RuntimeError(f"docker compose failed: {msg}")



def port_in_use(port: int) -> bool:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(("127.0.0.1", port)) == 0

def docker_stop_container(service: str) -> None:
    # deterministic compose container name: hbar-brain-<service>-1
    name = container_name_for_service(service)
    r = subprocess.run(["docker", "stop", name], capture_output=True, text=True)
    if r.returncode != 0:
        msg = ((r.stdout or "") + (r.stderr or "")).strip()
        raise RuntimeError(f"docker stop failed: {msg}")


class CreateBrainRequest(BaseModel):
    brain_id: str
    port: int | None = None

class RegisterBrainRequest(BaseModel):
    service: str
    port: int



def require_operator(token: str | None):
    if token != OPERATOR_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid operator token")

def fetch_json(url: str, timeout: float = 1.0):
    req = urllib.request.Request(url, headers={"accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))

def get_gateway_ip() -> str:
    """
    Deterministic gateway for BrainFoundry live checks.

    Host-run BrainFoundry (the supported lifecycle mode): default to 127.0.0.1.
    If BrainFoundry is ever containerized, you MUST set BRAINFOUNDRY_HOST_GATEWAY explicitly.
    """
    gw = os.getenv("BRAINFOUNDRY_HOST_GATEWAY", "").strip()
    if gw:
        return gw
    return "127.0.0.1"


def load_registry():
    # file lives inside the image at /app/brainfoundry/registry.json
    data = read_registry_doc()
    brains = data.get("brains", [])
    # normalize
    out = []
    for b in brains:
        out.append({
            "brain_id": b.get("brain_id"),
            "service": b.get("service"),
            "port": int(b.get("port")),
        })
    return out

@app.get("/health")
def health():
    return {"status": "ok", "service": "brainfoundry"}

@app.get("/brains")
def brains(x_operator_token: str | None = Header(default=None), include_state: bool = False):
    require_operator(x_operator_token)

    gw = get_gateway_ip()
    registry = load_registry()

    out = []
    for b in registry:
        brain_id = b["brain_id"]
        service = b["service"]
        port = int(b["port"])

        item = {
            "brain_id": brain_id,
            "service": service,
            "port": port,
        }

        if include_state:
            name = container_name_for_service(service)

            # container status
            container_exists = False
            running = False
            r = subprocess.run(["docker", "inspect", name], capture_output=True, text=True)
            if r.returncode == 0:
                container_exists = True
                r2 = subprocess.run(
                    ["docker", "inspect", "-f", "{{.State.Running}}", name],
                    capture_output=True,
                    text=True,
                )
                if r2.returncode == 0 and r2.stdout.strip() == "true":
                    running = True

            # healthcheck (only if running)
            reachable = False
            health = None
            url = f"http://{gw}:{port}/health"
            if running:
                try:
                    health = fetch_json(url, timeout=0.6)
                    reachable = True
                except Exception:
                    reachable = False
                    health = None

            item["state"] = {
                "container_exists": container_exists,
                "running": running,
                "reachable": reachable,
                "health_url": url,
            }
            if health is not None:
                item["state"]["health"] = health

        out.append(item)

    return {"brains": out}

@app.post("/brains")
def create_brain(req: CreateBrainRequest, x_operator_token: str | None = Header(default=None)):
    require_operator(x_operator_token)

    require_lifecycle()

    brain_id = (req.brain_id or "").strip()
    if not re.fullmatch(r"[a-z0-9]+(\.[a-z0-9]+)+", brain_id):
        audit_log("brains.create", brain_id=brain_id or None, ok=False, error="invalid brain_id")
        raise HTTPException(status_code=400, detail="Invalid brain_id format")

    if not brain_id.startswith("hbar.brain."):
        audit_log("brains.create", brain_id=brain_id, ok=False, error="brain_id must start with hbar.brain.")
        raise HTTPException(status_code=400, detail="brain_id must start with hbar.brain.")

    try:
        doc = read_registry_doc()
        brains = doc.get("brains", [])

        if any(b.get("brain_id") == brain_id for b in brains):
            audit_log("brains.create", brain_id=brain_id, ok=False, error="brain already exists")
            raise HTTPException(status_code=409, detail="Brain already exists")

        used_ports = sorted({int(b.get("port")) for b in brains if "port" in b})
        if req.port is not None:
            port = int(req.port)
            if port in used_ports:
                audit_log("brains.create", brain_id=brain_id, ok=False, error=f"port {port} already in registry")
                raise HTTPException(status_code=409, detail="Port already in use (registry)")
        else:
            # deterministic: next port = max + 10, starting at 8110
            port = (max(used_ports) + 10) if used_ports else 8110

        service = service_name_for(brain_id)

        # call instantiator primitives only (no shell)
        mold = SCRIPTS_DIR / "mold_new_brain.sh"
        reg = SCRIPTS_DIR / "register_instance.sh"

        audit_log("brains.create.request", brain_id=brain_id, ok=True, detail={"port": port, "service": service})

        r1 = subprocess.run(
            [str(mold), brain_id],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
        )
        if r1.returncode != 0:
            msg = (r1.stdout or "") + (r1.stderr or "")
            audit_log("brains.create", brain_id=brain_id, ok=False, error=f"mold_new_brain failed: {msg.strip()}")
            raise HTTPException(status_code=500, detail="Instantiator script failed")

        r2 = subprocess.run(
            [str(reg), brain_id, str(port), str(COMPOSE_FILE)],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
        )
        if r2.returncode != 0:
            msg = (r2.stdout or "") + (r2.stderr or "")
            audit_log("brains.create", brain_id=brain_id, ok=False, error=f"register_instance failed: {msg.strip()}")
            raise HTTPException(status_code=500, detail="Instantiator script failed")

        # registry update (deterministic sort by port)
        brains.append({"brain_id": brain_id, "service": service, "port": port})
        brains_sorted = sorted(brains, key=lambda b: int(b.get("port", 0)))
        doc["brains"] = brains_sorted
        write_registry_doc(doc)

        audit_log("brains.create", brain_id=brain_id, ok=True, detail={"port": port, "service": service})
        return {"ok": True, "brain_id": brain_id, "service": service, "port": port}

    except HTTPException:
        raise
    except Exception as e:
        audit_log("brains.create", brain_id=brain_id, ok=False, error=str(e))
        print(f"[brainfoundry] ERROR create_brain brain_id={brain_id} err={e!r}", flush=True)
        raise HTTPException(status_code=500, detail="Create brain failed")




def container_name_for_service(service: str) -> str:
    """
    Deterministic compose container name.

    docker compose names containers like:
      <project>-<service>-1

    Our project directory is repo-root "hbar-brain" so compose project name
    defaults to "hbar-brain" unless overridden.
    """
    return f"hbar-brain-{service}-1"



@app.post("/brains/{brain_id}/start")
def start_brain(brain_id: str, x_operator_token: str | None = Header(default=None)):
    require_operator(x_operator_token)
    require_lifecycle()

    with lifecycle_lock(brain_id):
        brain_id = (brain_id or "").strip()

        registry = load_registry()
        entry = next((b for b in registry if b["brain_id"] == brain_id), None)
        if not entry:
            audit_log("brains.delete.noop", brain_id=brain_id, ok=True)
            return {"ok": True, "brain_id": brain_id, "status": "already_deleted"}

        service = entry["service"]
        port = int(entry.get("port") or 0)

        # Fast preflight: avoid docker compose when port is already taken
        if port and port_in_use(port):
            audit_log("brains.start.port_in_use", brain_id=brain_id, ok=False, detail={"port": port})
            raise HTTPException(status_code=409, detail=f"port already allocated: {port}")

        name = container_name_for_service(service)

        # Container exists?
        r = subprocess.run(["docker", "inspect", name], capture_output=True, text=True)
        if r.returncode == 0:
            r2 = subprocess.run(
                ["docker", "inspect", "-f", "{{.State.Running}}", name],
                capture_output=True,
                text=True,
            )
            if r2.returncode == 0 and r2.stdout.strip() == "true":
                audit_log("brains.start.noop", brain_id=brain_id, ok=True)
                return {"ok": True, "brain_id": brain_id, "status": "already_running"}

            # exists but stopped -> resume
            r3 = subprocess.run(["docker", "start", name], capture_output=True, text=True)
            if r3.returncode != 0:
                msg = ((r3.stdout or "") + (r3.stderr or "")).strip()
                bind_conflict_markers = (
                    "port is already allocated",
                    "failed to bind host port",
                    "address already in use",
                )
                if any(m in msg for m in bind_conflict_markers):
                    audit_log("brains.start.port_in_use", brain_id=brain_id, ok=False, detail={"port": port})
                    raise HTTPException(status_code=409, detail=f"port already allocated: {port}")
                audit_log("brains.start", brain_id=brain_id, ok=False, error=msg)
                raise HTTPException(status_code=500, detail="Start failed")
            audit_log("brains.start.resume", brain_id=brain_id, ok=True)
            return {"ok": True, "brain_id": brain_id, "status": "resumed"}

        # No container -> compose up
        audit_log("brains.start.request", brain_id=brain_id, ok=True, detail={"service": service})
        try:
            docker_compose("up", "-d", "--build", service)
        except RuntimeError as e:
            msg = str(e)
            bind_conflict_markers = (
                "port is already allocated",
                "failed to bind host port",
                "address already in use",
            )
            if any(m in msg for m in bind_conflict_markers):
                audit_log("brains.start.port_in_use", brain_id=brain_id, ok=False, detail={"port": port})
                raise HTTPException(status_code=409, detail=f"port already allocated: {port}")
            audit_log("brains.start", brain_id=brain_id, ok=False, error=msg)
            raise HTTPException(status_code=500, detail="Start failed")

        audit_log("brains.start", brain_id=brain_id, ok=True, detail={"service": service})
        return {"ok": True, "brain_id": brain_id, "status": "started"}



@app.post("/brains/{brain_id}/stop")
def stop_brain(brain_id: str, x_operator_token: str | None = Header(default=None)):
    require_operator(x_operator_token)
    require_lifecycle()

    with lifecycle_lock(brain_id):
        registry = load_registry()
        entry = next((b for b in registry if b["brain_id"] == brain_id), None)
        if not entry:
            audit_log("brains.delete.noop", brain_id=brain_id, ok=True)
            return {"ok": True, "brain_id": brain_id, "status": "already_deleted"}

        service = entry["service"]
        name = container_name_for_service(service)

        # Inspect container
        r = subprocess.run(["docker", "inspect", name], capture_output=True, text=True)

        if r.returncode != 0:
            audit_log("brains.stop.noop", brain_id=brain_id, ok=True)
            return {"ok": True, "brain_id": brain_id, "status": "already_stopped"}

        r2 = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Running}}", name],
            capture_output=True,
            text=True,
        )

        if r2.returncode == 0 and r2.stdout.strip() != "true":
            audit_log("brains.stop.noop", brain_id=brain_id, ok=True)
            return {"ok": True, "brain_id": brain_id, "status": "already_stopped"}

        r3 = subprocess.run(["docker", "stop", name], capture_output=True, text=True)
        if r3.returncode != 0:
            msg = ((r3.stdout or "") + (r3.stderr or "")).strip()
            audit_log("brains.stop", brain_id=brain_id, ok=False, error=msg)
            raise HTTPException(status_code=500, detail="Stop failed")
        audit_log("brains.stop", brain_id=brain_id, ok=True)
        return {"ok": True, "brain_id": brain_id, "status": "stopped"}


@app.get("/brains/{brain_id}/status")
def brain_status(brain_id: str, x_operator_token: str | None = Header(default=None)):
    require_operator(x_operator_token)

    registry = load_registry()
    entry = next((b for b in registry if b["brain_id"] == brain_id), None)

    registered = entry is not None
    service = entry["service"] if entry else None

    container_exists = False
    running = False

    if service:
        name = container_name_for_service(service)
        r = subprocess.run(
            ["docker", "inspect", name],
            capture_output=True,
            text=True,
        )
        if r.returncode == 0:
            container_exists = True
            r2 = subprocess.run(
                ["docker", "inspect", "-f", "{{.State.Running}}", name],
                capture_output=True,
                text=True,
            )
            if r2.returncode == 0 and r2.stdout.strip() == "true":
                running = True

    return {
        "brain_id": brain_id,
        "service": service,
        "registered": registered,
        "container_exists": container_exists,
        "running": running,
    }


@app.get("/brains/{brain_id}/healthcheck")
def brain_healthcheck(brain_id: str, x_operator_token: str | None = Header(default=None)):
    require_operator(x_operator_token)

    registry = load_registry()
    entry = next((b for b in registry if b["brain_id"] == brain_id), None)
    if not entry:
        raise HTTPException(status_code=404, detail="Brain not found")

    gw = get_gateway_ip()
    port = int(entry["port"])
    url = f"http://{gw}:{port}/health"

    try:
        data = fetch_json(url, timeout=1.0)
        return {
            "brain_id": brain_id,
            "url": url,
            "reachable": True,
            "response": data,
        }
    except Exception as e:
        return {
            "brain_id": brain_id,
            "url": url,
            "reachable": False,
            "error": str(e),
        }

@app.delete("/brains/{brain_id}")
def delete_brain(brain_id: str, x_operator_token: str | None = Header(default=None)):
    require_operator(x_operator_token)
    require_lifecycle()

    with lifecycle_lock(brain_id):
        registry = load_registry()
        entry = next((b for b in registry if b["brain_id"] == brain_id), None)
        if not entry:
            audit_log("brains.delete.noop", brain_id=brain_id, ok=True)
            return {"ok": True, "brain_id": brain_id, "status": "already_deleted"}

        service = entry["service"]

        audit_log("brains.delete.request", brain_id=brain_id, ok=True, detail={"service": service})

        try:
            # 1) best-effort stop
            try:
                try:
                    docker_compose("stop", service)
                except RuntimeError as e:
                    if "no such service" in str(e):
                        docker_stop_container(service)
                    else:
                        raise
            except Exception:
                pass

            # 2) best-effort container remove
            r_rm = subprocess.run(
                ["docker", "rm", "-f", container_name_for_service(service)],
                capture_output=True,
                text=True,
            )
            if r_rm.returncode != 0:
                msg = ((r_rm.stdout or "") + (r_rm.stderr or "")).strip()
                if "No such container" not in msg:
                    raise RuntimeError(f"docker rm failed: {msg}")

            # 3) unregister from compose
            r = subprocess.run(
                [str(REPO_ROOT / "scripts" / "unregister_instance.sh"),
                 brain_id,
                 str(COMPOSE_FILE)],
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
            )
            if r.returncode != 0:
                msg = ((r.stdout or "") + (r.stderr or "")).strip()
                if "service" in msg and "not found" in msg:
                    audit_log("brains.delete.compose_absent", brain_id=brain_id, ok=True, detail={"service": service})
                else:
                    raise RuntimeError(f"unregister failed: {msg}")

            # 4) update registry.json
            new_brains = [b for b in registry if b["brain_id"] != brain_id]
            write_registry_doc({"brains": new_brains})

            # 5) remove instance directory (deterministic)
            inst_dir = REPO_ROOT / "instances" / brain_id
            if inst_dir.exists():
                import shutil
                try:
                    shutil.rmtree(inst_dir)
                except Exception as e:
                    raise RuntimeError(f"instance directory removal failed: {e}")

            audit_log("brains.delete", brain_id, ok=True)
            return {"ok": True, "brain_id": brain_id}

        except Exception as e:
            audit_log("brains.delete", brain_id, ok=False, error=str(e))
            raise HTTPException(status_code=500, detail="Delete failed")

