import { useState, useRef } from "react";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

export default function Upload() {
  const [files, setFiles] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [log, setLog] = useState([]);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const inputRef = useRef(null);

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
      try {
        const r = await fetch(`${API_BASE}/documents/upload`, {
          method: "POST",
          body: fd,
        });
        if (!r.ok) throw new Error(`${r.status}`);
        const j = await r.json();
        pushLog(`✅ ${file.name}: ${j?.chunks?.length ?? 0} chunk(s)`);
      } catch (err) {
        pushLog(`❌ ${file.name}: ${err.message}`);
      }
    }
    setUploading(false);
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
    <div style={{ maxWidth: 900, margin: "40px auto", fontFamily: "ui-sans-serif, system-ui" }}>
      <h1 style={{ fontSize: 28, fontWeight: 700 }}>hbar brain — Upload & Search</h1>

      <section style={{ marginTop: 24, padding: 16, border: "1px solid #ddd", borderRadius: 12 }}>
        <div
          onDrop={onDrop}
          onDragOver={prevent}
          onDragEnter={prevent}
          style={{
            border: "2px dashed #aaa",
            padding: 24,
            borderRadius: 12,
            textAlign: "center",
            background: "#fafafa",
          }}
        >
          <p style={{ marginBottom: 12 }}>Drag files here or</p>
          <button onClick={() => inputRef.current?.click()} style={{ padding: "8px 14px" }}>
            Choose files
          </button>
          <input
            ref={inputRef}
            type="file"
            multiple
            onChange={onSelect}
            style={{ display: "none" }}
          />
        </div>

        {!!files.length && (
          <div style={{ marginTop: 12, fontSize: 14 }}>
            <strong>Selected:</strong> {files.map(f => f.name).join(", ")}
          </div>
        )}

        <div style={{ marginTop: 16 }}>
          <button onClick={upload} disabled={uploading || !files.length} style={{ padding: "8px 14px" }}>
            {uploading ? "Uploading…" : "Upload"}
          </button>
        </div>

        {!!log.length && (
          <pre style={{ marginTop: 16, background: "#f6f6f6", padding: 12, borderRadius: 8, whiteSpace: "pre-wrap" }}>
{log.join("\n")}
          </pre>
        )}
      </section>

      <section style={{ marginTop: 24, padding: 16, border: "1px solid #ddd", borderRadius: 12 }}>
        <div style={{ display: "flex", gap: 8 }}>
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder='Search… (e.g., "VQE regularization")'
            style={{ flex: 1, padding: 10, border: "1px solid #ccc", borderRadius: 8 }}
          />
          <button onClick={runSearch} style={{ padding: "8px 14px" }}>Search</button>
        </div>

        {!!results.length && (
          <div style={{ marginTop: 16 }}>
            {results.map((r, i) => (
              <div key={i} style={{ padding: 12, border: "1px solid #eee", borderRadius: 8, marginBottom: 10 }}>
                <div style={{ fontSize: 12, color: "#666" }}>{r.document_name}</div>
                <div>{r.content}</div>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
