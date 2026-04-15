import { useState, useRef, useEffect } from "react";

// Use the internal Next.js proxy so the API key is forwarded server-side
const API_BASE = "/api/bf";

// Warm-academic palette to match nav + settings
const BG = "#0e0c0b";
const SURFACE = "#161310";
const BORDER = "#2a2420";
const TEXT = "#e8e0d5";
const MUTED = "#6b5f52";
const ACCENT = "#c9a96e";
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
  const [uploading, setUploading] = useState(false);
  const [log, setLog] = useState([]);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [layers, setLayers] = useState([]);
  const [layer, setLayer] = useState("");
  const [stats, setStats] = useState(null);
  const inputRef = useRef(null);

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

  const pushLog = (m) => setLog((x) => [...x, m]);
  const onSelect = (e) => setFiles(Array.from(e.target.files || []));
  const onDrop = (e) => {
    e.preventDefault();
    setFiles(Array.from(e.dataTransfer.files || []));
  };
  const prevent = (e) => e.preventDefault();

  const upload = async () => {
    if (!files.length) return;
    setUploading(true);
    setLog([]);
    for (const file of files) {
      const fd = new FormData();
      fd.append("file", file);
      if (layer) fd.append("layer", layer);
      try {
        const r = await fetch(`${API_BASE}/documents/upload`, { method: "POST", body: fd });
        const body = await r.text();
        if (!r.ok) {
          pushLog(`FAIL ${file.name}: ${r.status} — ${body.slice(0, 200)}`);
          continue;
        }
        const j = JSON.parse(body);
        const scope = j.layer ? ` → layer=${j.layer}` : " (unscoped)";
        pushLog(`OK ${file.name}: ${j?.chunks_created ?? 0} chunk(s)${scope}`);
      } catch (err) {
        pushLog(`FAIL ${file.name}: ${err.message}`);
      }
    }
    setUploading(false);
    loadStats();
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

      <section style={{ padding: 20, border: `1px solid ${BORDER}`, background: SURFACE, borderRadius: 12, marginBottom: 24 }}>
        <div
          onDrop={onDrop}
          onDragOver={prevent}
          onDragEnter={prevent}
          style={{
            border: `2px dashed ${BORDER}`,
            padding: 28,
            borderRadius: 12,
            textAlign: "center",
            background: BG,
          }}
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
          <button onClick={upload} disabled={uploading || !files.length} style={{ ...BTN, opacity: (uploading || !files.length) ? 0.4 : 1, cursor: (uploading || !files.length) ? "not-allowed" : "pointer" }}>
            {uploading ? "Uploading…" : "Upload"}
          </button>
        </div>

        {layers.length === 0 && (
          <div style={{ marginTop: 10, fontSize: 12, color: MUTED, fontStyle: "italic" }}>
            No layers defined yet. Add some in Settings → Memory layers to scope uploads.
          </div>
        )}

        {!!log.length && (
          <pre style={{ marginTop: 16, background: BG, border: `1px solid ${BORDER}`, color: TEXT, padding: 12, borderRadius: 8, whiteSpace: "pre-wrap", fontSize: 12, fontFamily: "DM Mono, monospace" }}>
{log.join("\n")}
          </pre>
        )}
      </section>

      {stats && (
        <section style={{ padding: 20, border: `1px solid ${BORDER}`, background: SURFACE, borderRadius: 12, marginBottom: 24 }}>
          <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginBottom: 12 }}>
            <h2 style={{ fontSize: 15, fontFamily: "Lora, Georgia, serif", margin: 0, color: TEXT }}>What your brain knows</h2>
            <div style={{ fontSize: 12, color: MUTED, fontFamily: "DM Mono, monospace" }}>
              {stats.unique_documents ?? 0} docs &middot; {stats.total_chunks ?? 0} chunks
            </div>
          </div>
          {stats.recent_documents?.length ? (
            <div>
              {stats.recent_documents.map((d, i) => (
                <div key={i} style={{ padding: "8px 12px", border: `1px solid ${BORDER}`, borderRadius: 6, marginBottom: 6, background: BG, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span style={{ color: TEXT, fontFamily: "DM Mono, monospace", fontSize: 12 }}>{d.name}</span>
                  <span style={{ color: MUTED, fontSize: 11 }}>{d.chunks} chunks{d.last_updated ? ` · ${new Date(d.last_updated).toLocaleDateString()}` : ""}</span>
                </div>
              ))}
            </div>
          ) : (
            <div style={{ color: MUTED, fontSize: 13, fontStyle: "italic" }}>Nothing ingested yet. Upload a file above.</div>
          )}
        </section>
      )}

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
