import { useState, useRef, useEffect } from "react";
import CustomSelect from "../lib/CustomSelect";

const API_BASE = "/api/bf";

const BG = "#0e0c0b";
const SURFACE = "#161310";
const BORDER = "#2a2420";
const TEXT = "#e8e0d5";
const MUTED = "#6b5f52";
const ACCENT = "#c9a96e";
const APPROVE = "#7a9e6e";
const REJECT = "#a96e6e";

// Layer-tier color mapping (Fix 1.5). Locked semantic association:
// identity=amber (brand-aligned), thinking=slate-blue, projects=sage-green,
// writing=mauve, episodic=warm-muted-gray. Anything outside the canonical
// five layers falls back to LAYER_DEFAULT so unknown layers still render.
const LAYER_COLORS = {
  identity: "#c9a96e",
  thinking: "#6b8eb3",
  projects: "#88a878",
  writing:  "#b78dad",
  episodic: "#6b5f52",
};
const LAYER_DEFAULT = "#6b5f52";

// Resolve a layer name to a color. Lowercase + strip trailing 's' so
// operator-defined plurals (observed: "writings" instead of "writing")
// still hit the canonical mapping without us listing every variant.
// Unknown layers fall back to LAYER_DEFAULT (the same warm gray as
// episodic — visually unobtrusive when the tier isn't recognized).
const layerColor = (l) => {
  if (!l) return LAYER_DEFAULT;
  const norm = String(l).toLowerCase().replace(/s$/, "");
  return LAYER_COLORS[norm] || LAYER_DEFAULT;
};

const INPUT = {
  background: "#0e0c0b",
  border: `1px solid ${BORDER}`,
  borderRadius: 8,
  color: TEXT,
  padding: "8px 10px",
  fontFamily: "DM Mono, monospace",
  fontSize: 13,
  outline: "none",
};
const BTN = {
  background: ACCENT,
  color: "#0e0c0b",
  border: "none",
  borderRadius: 8,
  padding: "8px 14px",
  fontWeight: 600,
  cursor: "pointer",
};

export default function Upload() {
  const [files, setFiles] = useState([]);
  const [busy, setBusy] = useState(false);
  const [log, setLog] = useState([]);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [layers, setLayers] = useState([]);
  const [layer, setLayer] = useState("");
  const [stats, setStats] = useState(null);
  const [pending, setPending] = useState([]); // [{proposal_id, file, layer, filename, deciding}]
  const [layerFilter, setLayerFilter] = useState(null); // null = no filter; click a badge to set, click again to clear
  const [pasteText, setPasteText] = useState("");   // paste-text path — alternative to file upload
  const [pasteTitle, setPasteTitle] = useState("");
  // Browse view: full doc list grouped by memory layer + "unlayered" bucket.
  // GET /documents?limit=N is a soft ceiling, NOT an assumption — past ~500 docs
  // the layer counts here are derived from this list, so an undersized limit
  // silently undercounts every layer. We request a high ceiling and surface
  // "showing N of TOTAL" if a brain ever exceeds it. Reloaded after every
  // ingest/forget.
  const [allDocs, setAllDocs] = useState(null); // null = not loaded yet, [] = empty
  const [allDocsTotal, setAllDocsTotal] = useState(0); // backend's full COUNT (may exceed the fetched page)
  const [allDocsLoading, setAllDocsLoading] = useState(false);
  // Per-layer expand/collapse state. Default: collapsed; "(unlayered)" opens
  // automatically because it's the operator's "needs organizing" queue.
  const [expandedLayers, setExpandedLayers] = useState(new Set(["(unlayered)"]));
  const toggleExpanded = (l) => setExpandedLayers(prev => {
    const next = new Set(prev);
    if (next.has(l)) next.delete(l); else next.add(l);
    return next;
  });

  // Trash bin: soft-deleted documents. Forget now sets metadata.deleted_at
  // rather than hard-deleting; the docs sit here until Restore (clears the
  // flag) or Empty Trash (the only actually-destructive action).
  const [trash, setTrash] = useState([]);
  const [trashExpanded, setTrashExpanded] = useState(false);
  const inputRef = useRef(null);
  const folderInputRef = useRef(null);

  // LayerBadge — pill rendering of a memory-tier label. Clicking toggles
  // the active filter for the whole Knowledge tab (recent-docs panel +
  // search). Active state inverts colors so the chosen filter is obvious.
  const LayerBadge = ({ layer, active, onClick }) => {
    const color = layerColor(layer);
    return (
      <span
        onClick={onClick ? (e) => { e.stopPropagation(); onClick(); } : undefined}
        role={onClick ? "button" : undefined}
        tabIndex={onClick ? 0 : undefined}
        title={onClick ? (active ? `Clear filter: ${layer}` : `Filter by ${layer}`) : layer}
        style={{
          display: "inline-flex",
          alignItems: "center",
          background: active ? color : color + "22",
          color: active ? "#0e0c0b" : color,
          fontFamily: "DM Mono, monospace",
          fontSize: 10,
          fontWeight: active ? 700 : 500,
          padding: "2px 8px",
          borderRadius: 999,
          border: `1px solid ${color}66`,
          cursor: onClick ? "pointer" : "default",
          textTransform: "lowercase",
          letterSpacing: "0.05em",
          userSelect: "none",
          whiteSpace: "nowrap",
        }}
      >
        {layer}
      </span>
    );
  };

  const toggleLayerFilter = (l) => setLayerFilter(prev => prev === l ? null : l);

  // Set the folder-mode attributes via DOM after mount — React strips unknown
  // HTML attributes like `webkitdirectory` in some versions.
  useEffect(() => {
    if (folderInputRef.current) {
      folderInputRef.current.setAttribute("webkitdirectory", "");
      folderInputRef.current.setAttribute("directory", "");
      folderInputRef.current.setAttribute("mozdirectory", "");
    }
  }, []);

  // Hydrate the Pending panel from the server on mount. Proposals created by
  // external surfaces (MCP write-side workers, the CLI, another browser tab)
  // are not in this component's local state — without this fetch the operator
  // would never see them and the MCP write-side chat would block forever
  // waiting for an approval that has no visible button.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const r = await fetch(`${API_BASE}/memory/proposals?status=PENDING&limit=100`, { cache: "no-store" });
        if (!r.ok) return;
        const data = await r.json();
        const items = Array.isArray(data?.proposals) ? data.proposals : [];
        const docs = items
          .filter(p => p.memory_type === "document_embedding")
          .map(p => ({
            proposal_id: p.proposal_id,
            filename: p.source_refs?.filename || "(unnamed)",
            layer: p.source_refs?.layer || "",
            deciding: false,
          }));
        if (cancelled || docs.length === 0) return;
        setPending(prev => {
          const seen = new Set(prev.map(x => x.proposal_id));
          const fresh = docs.filter(d => !seen.has(d.proposal_id));
          return [...prev, ...fresh];
        });
      } catch {
        // Silent — pending panel just stays empty if the proxy can't reach NodeOS.
      }
    })();
    return () => { cancelled = true; };
  }, []);

  // Filter hidden files (.git, .env, .DS_Store, etc.) and obvious binaries we
  // don't want indexing into a memory layer. Buyers folder-uploading hbar.world
  // would otherwise drag the entire .git history in.
  const HIDDEN_DIR_PATTERN = /(^|\/)(\.git|\.svn|\.hg|node_modules|__pycache__|\.next|\.venv|venv|dist|build)(\/|$)/i;
  const HIDDEN_FILE_PATTERN = /(^|\/)\.(env|ds_store|gitignore|gitattributes|dockerignore)/i;
  const filterHidden = (fileList) => {
    return fileList.filter(f => {
      const path = f.webkitRelativePath || f.name;
      if (HIDDEN_DIR_PATTERN.test(path)) return false;
      if (HIDDEN_FILE_PATTERN.test(path)) return false;
      return true;
    });
  };

  const pushLog = (m) => setLog((x) => [m, ...x].slice(0, 20));

  const loadStats = () => {
    fetch(`${API_BASE}/documents/stats`)
      .then(r => r.ok ? r.json() : null)
      .then(d => setStats(d))
      .catch(() => {});
  };

  // Browse view loader: GET /documents returns every document with name,
  // chunks, last_updated, layers array, source. We do the layer grouping
  // client-side so the operator can expand/collapse a layer without
  // re-fetching — backend stays simple, UI handles presentation.
  const loadAllDocs = () => {
    setAllDocsLoading(true);
    fetch(`${API_BASE}/documents?limit=10000`)
      .then(r => r.ok ? r.json() : null)
      .then(d => {
        setAllDocs(d?.documents || []);
        setAllDocsTotal(typeof d?.total === "number" ? d.total : (d?.documents || []).length);
      })
      .catch(() => { setAllDocs([]); setAllDocsTotal(0); })
      .finally(() => setAllDocsLoading(false));
  };

  // Trash loader. Reloaded after every soft-delete / restore / empty so the
  // bin stays in sync with the working set above.
  const loadTrash = () => {
    fetch(`${API_BASE}/documents/trash`)
      .then(r => r.ok ? r.json() : null)
      .then(d => setTrash(d?.documents || []))
      .catch(() => {});
  };

  const restoreDoc = async (name) => {
    try {
      const r = await fetch(`${API_BASE}/documents/${encodeURIComponent(name)}/restore`, { method: "POST" });
      if (r.ok) {
        const j = await r.json();
        pushLog(`RESTORED ${name}: ${j.chunks_restored ?? 0} chunk(s) back in working set`);
        loadStats(); loadAllDocs(); loadTrash();
      } else {
        const body = await r.text();
        pushLog(`FAIL restore ${name}: ${r.status} — ${body.slice(0, 200)}`);
      }
    } catch (err) {
      pushLog(`FAIL restore ${name}: ${err.message}`);
    }
  };

  const emptyTrash = async () => {
    if (!trash.length) return;
    if (!confirm(`Permanently delete ${trash.length} document${trash.length === 1 ? '' : 's'} from the trash?\n\nThis removes every chunk for good. Cannot be undone.`)) return;
    try {
      const r = await fetch(`${API_BASE}/documents/trash/empty`, { method: "POST" });
      if (r.ok) {
        const j = await r.json();
        pushLog(`TRASH EMPTIED: ${j.chunks_deleted ?? 0} chunk(s) permanently removed`);
        loadStats(); loadAllDocs(); loadTrash();
      } else {
        const body = await r.text();
        pushLog(`FAIL empty trash: ${r.status} — ${body.slice(0, 200)}`);
      }
    } catch (err) {
      pushLog(`FAIL empty trash: ${err.message}`);
    }
  };

  useEffect(() => {
    fetch(`${API_BASE}/settings/memory-layers`)
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d?.layers) setLayers(d.layers); })
      .catch(() => {});
    loadStats();
    loadAllDocs();
    loadTrash();
  }, []);

  const onSelect = (e) => setFiles(filterHidden(Array.from(e.target.files || [])));
  const onDrop = (e) => { e.preventDefault(); setFiles(filterHidden(Array.from(e.dataTransfer.files || []))); };
  const prevent = (e) => e.preventDefault();

  // Paste-text path: turn pasted text into an in-memory .md file and add it to
  // the upload list, so it flows through the exact same propose → approve
  // ingestion as a dropped file (same layer, same governance, same retrieval).
  const addPastedText = () => {
    const text = pasteText.trim();
    if (!text) return;
    const slug = (pasteTitle.trim() || `pasted-${new Date().toISOString().slice(0, 10)}`)
      .replace(/[^a-zA-Z0-9_-]+/g, "-").replace(/^-+|-+$/g, "").toLowerCase() || "pasted-note";
    const file = new File([text], `${slug}.md`, { type: "text/markdown" });
    setFiles((f) => [...f, file]);
    setPasteText("");
    setPasteTitle("");
    pushLog(`Added pasted text as ${slug}.md — Propose for ingestion below.`);
  };

  // Step 1: request a loop permit, then propose each file → get proposal_id back.
  const propose = async () => {
    if (!files.length) return;
    setBusy(true);
    try {
      const pr = await fetch("/api/permit", { method: "POST" });
      if (!pr.ok) { pushLog(`FAIL permit request: ${pr.status}`); setBusy(false); return; }
      const { permit_id } = await pr.json();

      const newPending = [];
      for (const file of files) {
        const fd = new FormData();
        fd.append("file", file);
        fd.append("permit_id", permit_id);
        if (layer) fd.append("layer", layer);
        try {
          const r = await fetch(`${API_BASE}/documents/upload`, { method: "POST", body: fd });
          const body = await r.text();
          if (r.status === 202) {
            const j = JSON.parse(body);
            newPending.push({ proposal_id: j.proposal_id, file, layer, filename: file.name, injectionScan: j.injection_scan || null });
            pushLog(`PROPOSED ${file.name} → awaiting your approval below`);
            const sc = j.injection_scan;
            if (sc && (sc.risk === "high" || sc.risk === "medium")) {
              pushLog(`⚠ ${file.name}: ${sc.risk.toUpperCase()} injection risk — ${sc.summary}`);
            }
          } else if (r.ok) {
            pushLog(`OK ${file.name} (already approved)`);
          } else {
            pushLog(`FAIL ${file.name}: ${r.status} — ${body.slice(0, 200)}`);
          }
        } catch (err) {
          pushLog(`FAIL ${file.name}: ${err.message}`);
        }
      }
      setPending(p => [...newPending, ...p]);
      setFiles([]);
    } finally {
      setBusy(false);
    }
  };

  // Step 2: approve → tell the server to persist (no file re-upload — text was
  // saved server-side on propose, keyed by proposal_id).
  const decide = async (idx, decision) => {
    setPending(p => p.map((x, i) => i === idx ? { ...x, deciding: true } : x));
    const prop = pending[idx];
    try {
      const d = await fetch("/api/proposal-decide", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ proposal_id: prop.proposal_id, decision, decided_by: "operator" }),
      });
      if (!d.ok) {
        const body = await d.text();
        pushLog(`FAIL decide ${prop.filename}: ${d.status} — ${body.slice(0, 200)}`);
        setPending(p => p.map((x, i) => i === idx ? { ...x, deciding: false } : x));
        return;
      }

      if (decision === "APPROVE") {
        const fd = new FormData();
        fd.append("proposal_id", prop.proposal_id);
        if (prop.layer) fd.append("layer", prop.layer);
        const r = await fetch(`${API_BASE}/documents/upload`, { method: "POST", body: fd });

        if (!r.ok) {
          const body = await r.text();
          pushLog(`FAIL ingest ${prop.filename}: ${r.status} — ${body.slice(0, 200)}`);
        } else {
          // Server streams Server-Sent Events: started, chunked, progress*, done|error.
          // Update p.progress in pending state so the Approve button shows live N/total.
          pushLog(`INGESTING ${prop.filename}: starting…`);
          const reader = r.body.getReader();
          const decoder = new TextDecoder();
          let buffer = "";
          let donePayload = null;
          let errorDetail = null;
          let lastLoggedDone = -1;
          while (true) {
            const { value, done } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            let sep;
            while ((sep = buffer.indexOf("\n\n")) !== -1) {
              const block = buffer.slice(0, sep);
              buffer = buffer.slice(sep + 2);
              const lines = block.split("\n");
              let evName = "message";
              let dataRaw = "";
              for (const line of lines) {
                if (line.startsWith("event:")) evName = line.slice(6).trim();
                else if (line.startsWith("data:")) dataRaw += line.slice(5).trim();
              }
              let data = null;
              try { data = JSON.parse(dataRaw); } catch { data = dataRaw; }
              if (evName === "chunked" && data?.total != null) {
                pushLog(`INGESTING ${prop.filename}: ${data.total} chunks queued`);
                setPending(p => p.map((x, j) => j === idx ? { ...x, progress: { done: 0, total: data.total } } : x));
              } else if (evName === "progress" && data?.done != null) {
                setPending(p => p.map((x, j) => j === idx ? { ...x, progress: { done: data.done, total: data.total, batch_seconds: data.batch_seconds } } : x));
                // Throttle log spam: log every 5 batches (or every batch when total <= 5).
                const stride = data.total <= 5 ? 1 : 5;
                if (data.done - lastLoggedDone >= stride * 32 || data.done === data.total) {
                  pushLog(`INGESTING ${prop.filename}: ${data.done}/${data.total} chunks (${data.batch_seconds}s/batch)`);
                  lastLoggedDone = data.done;
                }
              } else if (evName === "done") {
                donePayload = data;
              } else if (evName === "error") {
                errorDetail = data?.detail || JSON.stringify(data);
              }
            }
          }
          if (donePayload) {
            const scope = donePayload.layer ? ` → layer=${donePayload.layer}` : " (unscoped)";
            const total = donePayload.total_seconds != null ? ` in ${donePayload.total_seconds}s` : "";
            pushLog(`INGESTED ${prop.filename}: ${donePayload.chunks_created ?? 0} chunk(s)${scope}${total}`);
          } else if (errorDetail) {
            pushLog(`FAIL ingest ${prop.filename}: ${errorDetail}`);
          } else {
            pushLog(`FAIL ingest ${prop.filename}: stream ended without done event`);
          }
        }
      } else {
        pushLog(`REJECTED ${prop.filename}`);
      }

      setPending(p => p.filter((_, i) => i !== idx));
      loadStats();
      loadAllDocs();
    } catch (err) {
      pushLog(`FAIL decide ${prop.filename}: ${err.message}`);
      setPending(p => p.map((x, i) => i === idx ? { ...x, deciding: false } : x));
    }
  };

  const forgetDoc = async (name) => {
    if (!name) return;
    if (!confirm(`Move "${name}" to trash?\n\nThe brain stops using it for retrieval. You can restore it from the Trash panel below — only Empty Trash actually removes it.`)) return;
    try {
      const r = await fetch(`${API_BASE}/documents/${encodeURIComponent(name)}`, { method: "DELETE" });
      const body = await r.text();
      if (r.ok) {
        const j = JSON.parse(body);
        pushLog(`TRASHED ${name}: ${j.chunks_trashed ?? 0} chunk(s) moved to trash`);
        loadStats();
        loadAllDocs();
        loadTrash();
      } else {
        pushLog(`FAIL trash ${name}: ${r.status} — ${body.slice(0, 200)}`);
      }
    } catch (err) {
      pushLog(`FAIL trash ${name}: ${err.message}`);
    }
  };

  const runSearch = async () => {
    setResults([]);
    const body = { query, limit: 20 };
    if (layerFilter) body.layers = [layerFilter];
    const r = await fetch(`${API_BASE}/documents/search`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const j = await r.json();
    setResults(j.results || []);
  };

  // When the layer filter changes, re-run any active search so results
  // narrow to the chosen tier without operator re-typing the query.
  useEffect(() => {
    if (query.trim() && results.length) runSearch();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [layerFilter]);

  const forgetFromSearch = async (name) => {
    await forgetDoc(name);
    if (query.trim()) runSearch();
  };

  return (
    <div style={{ maxWidth: 900, margin: "40px auto", padding: "0 24px", fontFamily: "system-ui, -apple-system, sans-serif", color: TEXT }}>
      <h1 style={{ fontSize: 26, fontWeight: 600, fontFamily: "Lora, Georgia, serif", margin: "0 0 24px 0" }}>Knowledge — Upload &amp; Search</h1>

      {/* Empty-corpus guide — the cold-start fix. Shows only while the brain
          has no documents; disappears once the first knowledge is ingested. */}
      {stats && (stats.total_chunks || 0) === 0 && (stats.unique_documents || 0) === 0 && (
        <section style={{ padding: 18, border: `1px solid ${BORDER}`, background: SURFACE, borderRadius: 12, marginBottom: 24 }}>
          <div style={{ fontSize: 15, color: TEXT, marginBottom: 6 }}>Your brain knows nothing yet.</div>
          <div style={{ fontSize: 13, color: MUTED, lineHeight: 1.7 }}>
            <div>Add something below — paste text, or drop a file.</div>
            <div>The brain answers from what you give it; an empty brain has nothing to draw on.</div>
            <div style={{ marginTop: 8, color: TEXT }}>Good first things to add:</div>
            <ul style={{ margin: "4px 0 0 0", paddingLeft: 18 }}>
              <li>A note about who you are and what you&apos;re working on.</li>
              <li>A document, article, or paper you want the brain to know.</li>
              <li>Notes from a meeting, or a decision you just made.</li>
            </ul>
          </div>
        </section>
      )}

      {/* Upload */}
      <section style={{ padding: 20, border: `1px solid ${BORDER}`, background: SURFACE, borderRadius: 12, marginBottom: 24 }}>
        <div
          onDrop={onDrop}
          onDragOver={prevent}
          onDragEnter={prevent}
          style={{ border: `2px dashed ${BORDER}`, padding: 28, borderRadius: 12, textAlign: "center", background: BG }}
        >
          <p style={{ marginBottom: 12, color: MUTED, fontSize: 13 }}>Drag files or a folder here, or</p>
          <div style={{ display: "flex", gap: 10, justifyContent: "center", flexWrap: "wrap" }}>
            <button onClick={() => inputRef.current?.click()} style={BTN}>Choose files</button>
            <button onClick={() => folderInputRef.current?.click()} style={BTN}>Choose folder</button>
          </div>
          <input ref={inputRef} type="file" multiple onChange={onSelect} style={{ display: "none" }} />
          <input
            ref={folderInputRef}
            type="file"
            multiple
            onChange={onSelect}
            style={{ display: "none" }}
          />
          <p style={{ marginTop: 10, fontSize: 11, color: MUTED, fontStyle: "italic" }}>
            Folder upload includes all subdirectories. Hidden files (.git, .env, etc.) are skipped.
          </p>
        </div>

        {/* Paste text — alternative to file upload. The pasted text becomes an
            in-memory .md file and joins the same upload list + propose flow. */}
        <div style={{ marginTop: 14, paddingTop: 14, borderTop: `1px solid ${BORDER}` }}>
          <p style={{ marginBottom: 8, color: MUTED, fontSize: 13 }}>&hellip;or paste text directly:</p>
          <input
            type="text"
            value={pasteTitle}
            onChange={(e) => setPasteTitle(e.target.value)}
            placeholder="Title (e.g. About me, Meeting notes)"
            style={{ ...INPUT, width: "100%", boxSizing: "border-box", marginBottom: 8, fontFamily: "inherit" }}
          />
          <textarea
            value={pasteText}
            onChange={(e) => setPasteText(e.target.value)}
            placeholder="Paste anything your brain should know — notes, a document, facts about you…"
            rows={5}
            style={{ ...INPUT, width: "100%", boxSizing: "border-box", fontFamily: "inherit", resize: "vertical" }}
          />
          <button
            onClick={addPastedText}
            disabled={!pasteText.trim()}
            style={{ ...BTN, marginTop: 8, opacity: pasteText.trim() ? 1 : 0.5, cursor: pasteText.trim() ? "pointer" : "not-allowed" }}
          >Add pasted text</button>
        </div>

        {!!files.length && (
          <div style={{ marginTop: 12, fontSize: 13, color: MUTED }}>
            <span style={{ color: TEXT }}>Selected:</span> {files.map(f => f.name).join(", ")}
          </div>
        )}

        <div style={{ marginTop: 16, display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
          <label style={{ fontSize: 13, color: "var(--muted)", fontFamily: "var(--font-mono)" }}>Memory layer:</label>
          <CustomSelect
            value={layer}
            onChange={setLayer}
            title="Memory layer"
            minWidth={160}
            options={[
              { value: "", label: "(unscoped)" },
              ...layers.map(l => ({ value: l.name, label: l.name })),
            ]}
          />
          {(() => {
            const disabled = busy || !files.length;
            return (
              <button
                onClick={propose}
                disabled={disabled}
                style={{
                  padding: "12px 20px",
                  background: disabled ? "var(--surface)" : "var(--accent)",
                  color: disabled ? "var(--muted)" : "var(--bg)",
                  border: "1px solid var(--border)",
                  borderRadius: "10px",
                  cursor: disabled ? "not-allowed" : "pointer",
                  fontSize: "14px",
                  fontWeight: 600,
                  transition: "all 0.15s ease",
                  whiteSpace: "nowrap",
                  flexShrink: 0,
                }}
              >
                {busy ? "Proposing…" : "Propose for ingestion"}
              </button>
            );
          })()}
        </div>
        <div style={{ marginTop: 10, fontSize: 11, color: "var(--muted)", fontStyle: "italic", lineHeight: 1.6 }}>
          Uploads go through the governance kernel: propose first, then you approve below.
          This is what sovereignty looks like — nothing enters your brain&apos;s long-term memory
          without your explicit consent, and every ingestion is logged.
        </div>
        {layers.length === 0 && (
          <div style={{ marginTop: 8, fontSize: 12, color: MUTED, fontStyle: "italic" }}>
            No layers defined yet. Add some in Settings → Memory layers to scope uploads.
          </div>
        )}

        {!!log.length && (
          <pre style={{ marginTop: 16, background: BG, border: `1px solid ${BORDER}`, color: TEXT, padding: 12, borderRadius: 8, whiteSpace: "pre-wrap", fontSize: 12, fontFamily: "DM Mono, monospace", maxHeight: 160, overflow: "auto" }}>
{log.join("\n")}
          </pre>
        )}
      </section>

      {/* Pending proposals — the governance moment */}
      {pending.length > 0 && (
        <section style={{ padding: 20, border: `1px solid ${ACCENT}`, background: SURFACE, borderRadius: 12, marginBottom: 24 }}>
          <h2 style={{ fontSize: 15, fontFamily: "Lora, Georgia, serif", margin: "0 0 4px 0", color: ACCENT }}>Pending memory proposals</h2>
          <div style={{ fontSize: 12, color: MUTED, fontStyle: "italic", marginBottom: 14, lineHeight: 1.6 }}>
            Your NodeOS governance kernel is asking for explicit approval before writing each of these into long-term memory. Approve or reject.
          </div>
          {pending.map((p, i) => (
            <div key={p.proposal_id} style={{ padding: 14, border: `1px solid ${BORDER}`, borderRadius: 8, marginBottom: 10, background: BG }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 10 }}>
                <div>
                  <div style={{ color: TEXT, fontFamily: "DM Mono, monospace", fontSize: 13 }}>{p.filename}</div>
                  <div style={{ color: MUTED, fontSize: 11, marginTop: 4 }}>
                    layer: {p.layer || "(unscoped)"} · proposal: {p.proposal_id.slice(0, 8)}…
                  </div>
                </div>
                <div style={{ display: "flex", gap: 8 }}>
                  <button
                    onClick={() => decide(i, "APPROVE")}
                    disabled={p.deciding}
                    style={{ ...BTN, background: APPROVE, color: "#fff", opacity: p.deciding ? 0.4 : 1 }}
                  >
                    {p.deciding
                      ? (p.progress ? `embedding ${p.progress.done}/${p.progress.total}…` : "…")
                      : "Approve & ingest"}
                  </button>
                  <button
                    onClick={() => decide(i, "DENY")}
                    disabled={p.deciding}
                    style={{ ...BTN, background: "transparent", color: REJECT, border: `1px solid ${REJECT}`, opacity: p.deciding ? 0.4 : 1 }}
                  >
                    Reject
                  </button>
                </div>
              </div>
              {p.injectionScan && (p.injectionScan.risk === "high" || p.injectionScan.risk === "medium") && (
                <div style={{ marginTop: 12, padding: "10px 12px", borderRadius: 8, border: `1px solid ${p.injectionScan.risk === "high" ? "#d9777755" : "#c9a96e55"}`, background: p.injectionScan.risk === "high" ? "#1a0e0e" : "#15120c" }}>
                  <div style={{ color: p.injectionScan.risk === "high" ? "#d97777" : "#c9a96e", fontSize: 12, fontWeight: 600, marginBottom: 4 }}>
                    ⚠ Possible prompt injection ({p.injectionScan.risk} risk)
                  </div>
                  <div style={{ color: MUTED, fontSize: 11.5, lineHeight: 1.6, marginBottom: (p.injectionScan.signals || []).length ? 8 : 0 }}>
                    This document contains text that looks like instructions aimed at the AI, not at you.
                    Review the flagged passages before approving — approving ingests it into your brain's memory.
                  </div>
                  {(p.injectionScan.signals || []).slice(0, 4).map((s, si) => (
                    <div key={si} style={{ color: MUTED, fontSize: 11, fontFamily: "DM Mono, monospace", opacity: 0.8, lineHeight: 1.6, marginTop: 3 }}>
                      <span style={{ color: "#d97777", opacity: 0.8 }}>[{s.severity}]</span> {s.excerpt}
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
        </section>
      )}

      {/* What your brain knows */}
      {stats && (
        <section style={{ padding: 20, border: `1px solid ${BORDER}`, background: SURFACE, borderRadius: 12, marginBottom: 24 }}>
          <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginBottom: 12, gap: 10, flexWrap: "wrap" }}>
            <h2 style={{ fontSize: 15, fontFamily: "Lora, Georgia, serif", margin: 0, color: TEXT }}>What your brain knows</h2>
            <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
              {layerFilter && (
                <button
                  onClick={() => setLayerFilter(null)}
                  title="Clear layer filter"
                  style={{ background: "transparent", border: `1px solid ${BORDER}`, color: MUTED, borderRadius: 6, padding: "3px 8px", cursor: "pointer", fontSize: 11, fontFamily: "DM Mono, monospace" }}
                >
                  filter: {layerFilter} ×
                </button>
              )}
              <div style={{ fontSize: 12, color: MUTED, fontFamily: "DM Mono, monospace" }}>
                {stats.unique_documents ?? 0} docs · {stats.total_chunks ?? 0} chunks
              </div>
            </div>
          </div>
          {(() => {
            const recent = stats.recent_documents || [];
            const filtered = layerFilter ? recent.filter(d => (d.layers || []).includes(layerFilter)) : recent;
            if (!recent.length) {
              return <div style={{ color: MUTED, fontSize: 13, fontStyle: "italic" }}>Nothing ingested yet. Upload a file above.</div>;
            }
            if (!filtered.length) {
              return <div style={{ color: MUTED, fontSize: 13, fontStyle: "italic" }}>No recent docs in layer &quot;{layerFilter}&quot;. Search may surface more — every chunk is still queryable.</div>;
            }
            return (
              <div>
                {filtered.map((d, i) => (
                  <div key={i} style={{ padding: "8px 12px", border: `1px solid ${BORDER}`, borderRadius: 6, marginBottom: 6, background: BG, display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                    <span style={{ color: TEXT, fontFamily: "DM Mono, monospace", fontSize: 12, overflow: "hidden", textOverflow: "ellipsis", flex: "1 1 200px", minWidth: 0 }}>{d.name}</span>
                    <div style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0, flexWrap: "wrap" }}>
                      {(d.layers || []).map(l => (
                        <LayerBadge key={l} layer={l} active={layerFilter === l} onClick={() => toggleLayerFilter(l)} />
                      ))}
                      <span style={{ color: MUTED, fontSize: 11 }}>{d.chunks} chunks{d.last_updated ? ` · ${new Date(d.last_updated).toLocaleDateString()}` : ""}</span>
                      <button
                        onClick={() => forgetDoc(d.name)}
                        title={`Forget "${d.name}"`}
                        aria-label={`Forget ${d.name}`}
                        style={{ background: "transparent", border: `1px solid ${BORDER}`, color: REJECT, borderRadius: 6, padding: "4px 8px", cursor: "pointer", fontSize: 12, lineHeight: 1 }}
                      >
                        ×
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            );
          })()}
        </section>
      )}

      {/* Browse — full document list grouped by memory layer.
          Pairs with "What your brain knows" preview above: that surface
          is the at-a-glance recent-10; this is the deep view — every
          ingested document, grouped by the memory layer it lives in,
          with an explicit "(unlayered)" bucket for docs that were
          ingested without a layer tag. The unlayered bucket is the
          operator's "needs organizing" queue. */}
      {allDocs && allDocs.length > 0 && (
        <section style={{ padding: 20, border: `1px solid ${BORDER}`, background: SURFACE, borderRadius: 12, marginBottom: 24 }}>
          <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginBottom: 12, gap: 10, flexWrap: "wrap" }}>
            <h2 style={{ fontSize: 15, fontFamily: "Lora, Georgia, serif", margin: 0, color: TEXT }}>Browse — by memory layer</h2>
            <div style={{ fontSize: 12, color: MUTED, fontFamily: "DM Mono, monospace" }}>
              {allDocsTotal > allDocs.length
                ? `showing ${allDocs.length} of ${allDocsTotal} docs`
                : `${allDocs.length} ${allDocs.length === 1 ? "doc" : "docs"} total`}
            </div>
          </div>

          {(() => {
            // Group docs by layer. A doc with chunks across multiple layers
            // shows up under each one. Docs with no layer go under (unlayered).
            const byLayer = new Map();
            for (const doc of allDocs) {
              const docLayers = doc.layers && doc.layers.length ? doc.layers : ["(unlayered)"];
              for (const l of docLayers) {
                if (!byLayer.has(l)) byLayer.set(l, []);
                byLayer.get(l).push(doc);
              }
            }
            // Order: canonical layers (matches LAYER_COLORS) first in fixed
            // sequence, then operator-defined custom layers alphabetically,
            // then (unlayered) at the bottom as the residual bucket.
            const CANONICAL_ORDER = ["identity", "thinking", "projects", "writing", "episodic"];
            const layerKeys = Array.from(byLayer.keys());
            const canonical = CANONICAL_ORDER.filter(l => byLayer.has(l));
            const custom = layerKeys
              .filter(l => l !== "(unlayered)" && !CANONICAL_ORDER.includes(l))
              .sort();
            const unlayered = byLayer.has("(unlayered)") ? ["(unlayered)"] : [];
            const orderedLayers = [...canonical, ...custom, ...unlayered];

            return orderedLayers.map(layerName => {
              const docs = byLayer.get(layerName);
              const expanded = expandedLayers.has(layerName);
              const isUnlayered = layerName === "(unlayered)";
              return (
                <div key={layerName} style={{ marginBottom: 10, border: `1px solid ${BORDER}`, borderRadius: 8, background: BG, overflow: "hidden" }}>
                  <div
                    onClick={() => toggleExpanded(layerName)}
                    role="button"
                    tabIndex={0}
                    onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggleExpanded(layerName); } }}
                    style={{ padding: "10px 14px", display: "flex", justifyContent: "space-between", alignItems: "center", cursor: "pointer", gap: 10, flexWrap: "wrap", userSelect: "none" }}
                    title={expanded ? "Collapse" : "Expand"}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                      <span style={{ color: MUTED, fontSize: 11, width: 12, display: "inline-block" }}>{expanded ? "▾" : "▸"}</span>
                      {isUnlayered ? (
                        <span style={{ fontSize: 12, color: MUTED, fontFamily: "DM Mono, monospace", fontStyle: "italic" }}>(unlayered)</span>
                      ) : (
                        <LayerBadge layer={layerName} />
                      )}
                      <span style={{ color: TEXT, fontSize: 13 }}>
                        {docs.length} {docs.length === 1 ? "doc" : "docs"}
                      </span>
                    </div>
                    {isUnlayered && (
                      <span style={{ fontSize: 11, color: MUTED, fontStyle: "italic" }}>
                        no memory layer assigned — re-ingest with a layer to organize
                      </span>
                    )}
                  </div>
                  {expanded && (
                    <div style={{ borderTop: `1px solid ${BORDER}` }}>
                      {docs.map((d, i) => (
                        <div key={`${d.name}-${i}`} style={{ padding: "8px 14px", borderBottom: i < docs.length - 1 ? `1px solid ${BORDER}` : "none", display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 10, flexWrap: "wrap" }}>
                          <div style={{ flex: "1 1 200px", minWidth: 0, display: "flex", flexDirection: "column", gap: 3 }}>
                            <span style={{ color: TEXT, fontFamily: "DM Mono, monospace", fontSize: 12, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{d.name}</span>
                            {/* Cheap synopsis — first ~150 chars of the first
                                chunk. Makes the Browse list scannable without
                                opening each doc. LLM-generated synopses are a
                                future upgrade (one llm.complete per doc at
                                ingest time, stored in metadata.synopsis). */}
                            {d.synopsis && (
                              <span style={{ color: MUTED, fontSize: 11, lineHeight: 1.4, overflow: "hidden", textOverflow: "ellipsis", display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical" }}>
                                {d.synopsis.replace(/\s+/g, ' ').slice(0, 200).trim()}{d.synopsis.length > 200 ? '…' : ''}
                              </span>
                            )}
                          </div>
                          <div style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0, flexWrap: "wrap" }}>
                            {/* Show OTHER layers this doc is in (the current
                                layer is implicit from the group header). Click
                                a badge to filter the rest of the Knowledge tab
                                — same toggleLayerFilter as elsewhere. */}
                            {(d.layers || []).filter(l => l !== layerName).map(l => (
                              <LayerBadge key={l} layer={l} active={layerFilter === l} onClick={() => toggleLayerFilter(l)} />
                            ))}
                            <span style={{ color: MUTED, fontSize: 11 }}>{d.chunks} chunks{d.last_updated ? ` · ${new Date(d.last_updated).toLocaleDateString()}` : ""}</span>
                            <button
                              onClick={() => forgetDoc(d.name)}
                              title={`Forget "${d.name}"`}
                              aria-label={`Forget ${d.name}`}
                              style={{ background: "transparent", border: `1px solid ${BORDER}`, color: REJECT, borderRadius: 6, padding: "4px 8px", cursor: "pointer", fontSize: 12, lineHeight: 1 }}
                            >
                              ×
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              );
            });
          })()}
        </section>
      )}

      {/* Trash — soft-deleted documents.
          The × buttons across the Knowledge tab no longer hard-delete; they
          set metadata.deleted_at, the doc disappears from Browse / Search /
          /chat/rag retrieval, and lands here. Restore puts it back. Empty
          Trash is the only path to actually destroying rows — explicit,
          confirmed, irreversible from there. */}
      {trash.length > 0 && (
        <section style={{ padding: 20, border: `1px solid ${BORDER}`, background: SURFACE, borderRadius: 12, marginBottom: 24 }}>
          <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginBottom: 12, gap: 10, flexWrap: "wrap" }}>
            <h2
              onClick={() => setTrashExpanded(v => !v)}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setTrashExpanded(v => !v); } }}
              style={{ fontSize: 15, fontFamily: "Lora, Georgia, serif", margin: 0, color: TEXT, cursor: "pointer", userSelect: "none" }}
              title={trashExpanded ? "Collapse trash" : "Expand trash"}
            >
              {trashExpanded ? "▾" : "▸"} Trash &mdash; {trash.length} {trash.length === 1 ? "doc" : "docs"}
            </h2>
            <button
              onClick={emptyTrash}
              title="Permanently delete every trashed document"
              style={{ background: "transparent", border: `1px solid ${REJECT}66`, color: REJECT, borderRadius: 6, padding: "4px 10px", cursor: "pointer", fontSize: 11, fontFamily: "DM Mono, monospace" }}
              onMouseOver={e => e.currentTarget.style.background = "#1a0a0a"}
              onMouseOut={e => e.currentTarget.style.background = "transparent"}
            >
              Empty Trash
            </button>
          </div>
          {trashExpanded && trash.map((d, i) => (
            <div key={`${d.name}-${i}`} style={{ padding: "8px 12px", border: `1px solid ${BORDER}`, borderRadius: 6, marginBottom: 6, background: BG, display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
              <span style={{ color: MUTED, fontFamily: "DM Mono, monospace", fontSize: 12, overflow: "hidden", textOverflow: "ellipsis", flex: "1 1 200px", minWidth: 0, textDecoration: "line-through", textDecorationColor: BORDER }}>{d.name}</span>
              <div style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0, flexWrap: "wrap" }}>
                {(d.layers || []).map(l => (
                  <LayerBadge key={l} layer={l} />
                ))}
                <span style={{ color: MUTED, fontSize: 11 }}>{d.chunks} chunks · trashed {d.trashed_at ? new Date(d.trashed_at).toLocaleString() : ""}</span>
                <button
                  onClick={() => restoreDoc(d.name)}
                  title={`Restore "${d.name}"`}
                  style={{ background: "transparent", border: `1px solid ${APPROVE}66`, color: APPROVE, borderRadius: 6, padding: "4px 10px", cursor: "pointer", fontSize: 11, fontFamily: "DM Mono, monospace" }}
                  onMouseOver={e => e.currentTarget.style.background = "#0a1a0a"}
                  onMouseOut={e => e.currentTarget.style.background = "transparent"}
                >
                  Restore
                </button>
              </div>
            </div>
          ))}
        </section>
      )}

      {/* Search */}
      <section style={{ padding: 20, border: `1px solid ${BORDER}`, background: SURFACE, borderRadius: 12 }}>
        <div style={{ display: "flex", gap: 8 }}>
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && runSearch()}
            placeholder="Search this brain…"
            style={{ ...INPUT, flex: 1, fontFamily: "system-ui, sans-serif", fontSize: 14 }}
          />
          <button onClick={runSearch} style={BTN}>Search</button>
        </div>

        {!!results.length && (
          <div style={{ marginTop: 16 }}>
            {results.map((r, i) => {
              const resultLayer = r.metadata?.layer || null;
              return (
                <div key={i} style={{ padding: 12, border: `1px solid ${BORDER}`, borderRadius: 8, marginBottom: 10, background: BG }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                    <div style={{ fontSize: 12, color: ACCENT, fontFamily: "DM Mono, monospace", overflow: "hidden", textOverflow: "ellipsis", flex: "1 1 200px", minWidth: 0 }}>{r.document_name}</div>
                    <div style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0 }}>
                      {resultLayer && (
                        <LayerBadge
                          layer={resultLayer}
                          active={layerFilter === resultLayer}
                          onClick={() => toggleLayerFilter(resultLayer)}
                        />
                      )}
                      <button
                        onClick={() => forgetFromSearch(r.document_name)}
                        title={`Forget "${r.document_name}"`}
                        aria-label={`Forget ${r.document_name}`}
                        style={{ background: "transparent", border: `1px solid ${BORDER}`, color: REJECT, borderRadius: 6, padding: "4px 8px", cursor: "pointer", fontSize: 12, lineHeight: 1 }}
                      >
                        ×
                      </button>
                    </div>
                  </div>
                  <div style={{ fontSize: 13, color: TEXT, marginTop: 6, lineHeight: 1.6 }}>{r.content}</div>
                </div>
              );
            })}
          </div>
        )}
      </section>
    </div>
  );
}
