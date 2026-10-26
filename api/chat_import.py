"""Chat history import from the Knowledge page (2026-10-25).

The person uploads the zip ChatGPT or Claude mailed them; this runs the same
prep and select as scripts/import_chats.py (docs/IMPORT.md steps 2 and 3,
newest 50 by default) in a scratch folder under the api's runtime volume, then
hands every selected document to `propose`, which the route binds to the same
permit and proposal path as a Knowledge upload. Nothing goes into memory here:
each document comes back PENDING and waits for the person's approval.
"""
import importlib.util
import pathlib
import shutil
import uuid
import zipfile

NEWEST_DEFAULT = 50
NEWEST_MAX = 500
SAFE_RISK = ("", "none", "low")

_TOOL = None


def tool():
    """scripts/import_chats.py, loaded by path: /app/scripts in the container
    (api/Dockerfile copies it), the checkout's scripts/ elsewhere."""
    global _TOOL
    if _TOOL is None:
        path = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "import_chats.py"
        spec = importlib.util.spec_from_file_location("import_chats", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _TOOL = mod
    return _TOOL


class NotAnExport(ValueError):
    """The upload is not an export this can read; the message is for the person."""


def run(fileobj, runtime_dir, propose, newest=NEWEST_DEFAULT):
    """fileobj: the uploaded zip. propose(name, text) -> the upload's 202 body
    (proposal_id, injection_scan). Returns the counts the card shows."""
    ic = tool()
    newest = max(1, min(int(newest or NEWEST_DEFAULT), NEWEST_MAX))
    work = pathlib.Path(runtime_dir) / "chat_imports" / uuid.uuid4().hex
    work.mkdir(parents=True, exist_ok=True)
    try:
        src = work / "export.zip"
        with open(src, "wb") as out:
            shutil.copyfileobj(fileobj, out, 1 << 20)
        if not zipfile.is_zipfile(src):
            raise NotAnExport("That file is not a zip. Upload the zip from the export email as it came.")
        try:
            rows = ic.prep(src, work / "prep")
        except (ValueError, KeyError, zipfile.BadZipFile) as e:
            raise NotAnExport(f"The zip could not be read as a ChatGPT or Claude export ({e.__class__.__name__}).")
        convs = [r for r in rows if r["kind"] == "conversation"]
        if not convs:
            raise NotAnExport("No conversations found. The zip should hold conversations.json.")
        selected = ic.select_rows(rows, newest=newest)
        proposed, flagged, stopped = 0, 0, ""
        for r in selected:
            text = (work / "prep" / r["file"]).read_text(encoding="utf-8")
            try:
                res = propose(ic.doc_name(r), text)
            except Exception as e:  # the gate said no (NodeOS down, permit refused): stop, report
                stopped = str(getattr(e, "detail", "") or e)[:300]
                break
            proposed += 1
            if ((res.get("injection_scan") or {}).get("risk") or "") not in SAFE_RISK:
                flagged += 1
        return {
            "conversations": len(convs),
            "projects": len(rows) - len(convs),
            "selected": len(selected),
            "proposed": proposed,
            "flagged": flagged,
            "sources": sorted({r["source"] for r in convs}),
            "newest": newest,
            "manifest_id": ic.manifest_id(selected),
            "stopped": stopped,
        }
    finally:
        shutil.rmtree(work, ignore_errors=True)
