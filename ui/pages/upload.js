import { useState, useRef, useEffect } from "react";

const API_BASE = "/api/bf";

const BG = "#0e0c0b";
const SURFACE = "#161310";
const BORDER = "#2a2420";
const TEXT = "#e8e0d5";
const MUTED = "#6b5f52";
const ACCENT = "#c9a96e";
const APPROVE = "#7a9e6e";
const REJECT = "#a96e6e";

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
  const inputRef = useRef(null);

  const pushLog = (m) => setLog((x) => [m, ...x].slice(0, 20));

  const loadStats = () => {
    fetch(`${API_BASE}/documents/stats`)
      .then(r => r.ok ? r.json() : null)
      .then(d => setStats(d))
      .catch(() => {});
  };

  useEffect(() => {
    fetch(`${API_BASE}/settings/memory-layers`)
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d?.layers) setLayers(d.layers); })
      .catch(() => {});
    loadStats();
  }, []);

  const onSelect = (e) => setFiles(Array.from(e.target.files || []));
  const onDrop = (e) => { e.preventDefault(); setFiles(Array.from(e.dataTransfer.files || [])); };
  const prevent = (e) => e.preventDefault();

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
            newPending.push({ proposal_id: j.proposal_id, file, layer, filename: file.name });
            pushLog(`PROPOSED ${file.name} → awaiting your approval below`);
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

  // Step 2: approve → re-upload with proposal_id → chunks land.
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
        fd.append("file", prop.file);
        fd.append("proposal_id", prop.proposal_id);
        if (prop.layer) fd.append("layer", prop.layer);
        const r = await fetch(`${API_BASE}/documents/upload`, { method: "POST", body: fd });
        const body = await r.text();
        if (r.ok) {
          const j = JSON.parse(body);
          const scope = j.layer ? ` → layer=${j.layer}` : " (unscoped)";
          pushLog(`INGESTED ${prop.filename}: ${j?.chunks_created ?? 0} chunk(s)${scope}`);
        } else {
          pushLog(`FAIL ingest ${prop.filename}: ${r.status} — ${body.slice(0, 200)}`);
        }
      } else {
        pushLog(`REJECTED ${prop.filename}`);
      }

      setPending(p => p.filter((_, i) => i !== idx));
      loadStats();
    } catch (err) {
      pushLog(`FAIL decide ${prop.filename}: ${err.message}`);
      setPending(p => p.map((x, i) => i === idx ? { ...x, deciding: false } : x));
    }
  };

  const forgetDoc = async (name) => {
    if (!name) return;
    if (!confirm(`Forget "${name}" from your brain's memory?\n\nThis removes every chunk of this document. Cannot be undone.`)) return;
    try {
      const r = await fetch(`${API_BASE}/documents/${encodeURIComponent(name)}`, { method: "DELETE" });
      const body = await r.text();
      if (r.ok) {
        const j = JSON.parse(body);
        pushLog(`FORGOTTEN ${name}: ${j.chunks_deleted ?? 0} chunk(s) removed`);
        loadStats();
      } else {
        pushLog(`FAIL forget ${name}: ${r.status} — ${body.slice(0, 200)}`);
      }
    } catch (err) {
      pushLog(`FAIL forget ${name}: ${err.message}`);
    }
  };

  const runSearch = async () => {
    setResults([]);
    const r = await fetch(`${API_BASE}/documents/search`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, limit: 5 }),
    });
    const j = await r.json();
    setResults(j.results || []);
  };

  return (
    <div style={{ maxWidth: 900, margin: "40px auto", padding: "0 24px", fontFamily: "system-ui, -apple-system, sans-serif", color: TEXT }}>
      <h1 style={{ fontSize: 26, fontWeight: 600, fontFamily: "Lora, Georgia, serif", margin: "0 0 24px 0" }}>Knowledge — Upload &amp; Search</h1>

      {/* Upload */}
      <section style={{ padding: 20, border: `1px solid ${BORDER}`, background: SURFACE, borderRadius: 12, marginBottom: 24 }}>
        <div
          onDrop={onDrop}
          onDragOver={prevent}
          onDragEnter={prevent}
          style={{ border: `2px dashed ${BORDER}`, padding: 28, borderRadius: 12, textAlign: "center", background: BG }}
        >
          <p style={{ marginBottom: 12, color: MUTED, fontSize: 13 }}>Drag files here or</p>
          <button onClick={() => inputRef.current?.click()} style={BTN}>Choose files</button>
          <input ref={inputRef} type="file" multiple onChange={onSelect} style={{ display: "none" }} />
        </div>

        {!!files.length && (
          <div style={{ marginTop: 12, fontSize: 13, color: MUTED }}>
            <span style={{ color: TEXT }}>Selected:</span> {files.map(f => f.name).join(", ")}
          </div>
        )}

        <div style={{ marginTop: 16, display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
          <label style={{ fontSize: 13, color: MUTED }}>Memory layer:</label>
          <select value={layer} onChange={e => setLayer(e.target.value)} style={INPUT}>
            <option value="">(unscoped)</option>
            {layers.map(l => <option key={l.name} value={l.name}>{l.name}</option>)}
          </select>
          <button
            onClick={propose}
            disabled={busy || !files.length}
            style={{ ...BTN, opacity: (busy || !files.length) ? 0.4 : 1, cursor: (busy || !files.length) ? "not-allowed" : "pointer" }}
          >
            {busy ? "Proposing…" : "Propose for ingestion"}
          </button>
        </div>
        <div style={{ marginTop: 10, fontSize: 11, color: MUTED, fontStyle: "italic", lineHeight: 1.6 }}>
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
                    {p.deciding ? "…" : "Approve & ingest"}
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
            </div>
          ))}
        </section>
      )}

      {/* What your brain knows */}
      {stats && (
        <section style={{ padding: 20, border: `1px solid ${BORDER}`, background: SURFACE, borderRadius: 12, marginBottom: 24 }}>
          <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginBottom: 12 }}>
            <h2 style={{ fontSize: 15, fontFamily: "Lora, Georgia, serif", margin: 0, color: TEXT }}>What your brain knows</h2>
            <div style={{ fontSize: 12, color: MUTED, fontFamily: "DM Mono, monospace" }}>
              {stats.unique_documents ?? 0} docs · {stats.total_chunks ?? 0} chunks
            </div>
          </div>
          {stats.recent_documents?.length ? (
            <div>
              {stats.recent_documents.map((d, i) => (
                <div key={i} style={{ padding: "8px 12px", border: `1px solid ${BORDER}`, borderRadius: 6, marginBottom: 6, background: BG, display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10 }}>
                  <span style={{ color: TEXT, fontFamily: "DM Mono, monospace", fontSize: 12, overflow: "hidden", textOverflow: "ellipsis" }}>{d.name}</span>
                  <div style={{ display: "flex", alignItems: "center", gap: 10, flexShrink: 0 }}>
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
          ) : (
            <div style={{ color: MUTED, fontSize: 13, fontStyle: "italic" }}>Nothing ingested yet. Upload a file above.</div>
          )}
        </section>
      )}

      {/* Search */}
      <section style={{ padding: 20, border: `1px solid ${BORDER}`, background: SURFACE, borderRadius: 12 }}>
        <div style={{ display: "flex", gap: 8 }}>
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && runSearch()}
            placeholder='Search… (e.g., "VQE regularization")'
            style={{ ...INPUT, flex: 1, fontFamily: "system-ui, sans-serif", fontSize: 14 }}
          />
          <button onClick={runSearch} style={BTN}>Search</button>
        </div>

        {!!results.length && (
          <div style={{ marginTop: 16 }}>
            {results.map((r, i) => (
              <div key={i} style={{ padding: 12, border: `1px solid ${BORDER}`, borderRadius: 8, marginBottom: 10, background: BG }}>
                <div style={{ fontSize: 12, color: ACCENT, fontFamily: "DM Mono, monospace" }}>{r.document_name}</div>
                <div style={{ fontSize: 13, color: TEXT, marginTop: 6, lineHeight: 1.6 }}>{r.content}</div>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
