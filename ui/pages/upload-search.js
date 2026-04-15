import { useState, useEffect } from 'react';

const API_BASE = '/api/bf';

const card = {
  background: '#fff',
  border: '1px solid #e5e5e5',
  borderRadius: 12,
  padding: 24,
  boxShadow: '0 1px 3px rgba(0,0,0,0.07)',
};

export default function UploadSearch() {
  const [dragActive, setDragActive] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [uploadedFiles, setUploadedFiles] = useState([]);

  const [searchQuery, setSearchQuery] = useState('');
  const [searchLimit, setSearchLimit] = useState(5);
  const [searchResults, setSearchResults] = useState([]);
  const [expandedResult, setExpandedResult] = useState(null);

  const [indexStatus, setIndexStatus] = useState(null);
  const [layers, setLayers] = useState([]);
  const [layer, setLayer] = useState('');

  useEffect(() => {
    fetch(`${API_BASE}/settings/memory-layers`)
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d?.layers) setLayers(d.layers); })
      .catch(() => {});
  }, []);

  const loadIndexStatus = async () => {
    try {
      const r = await fetch(`${API_BASE}/documents/stats`);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      setIndexStatus(await r.json());
    } catch (err) {
      console.error('Failed to load index status:', err);
    }
  };

  useEffect(() => { loadIndexStatus(); }, []);

  const handleDrag = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') setDragActive(true);
    else if (e.type === 'dragleave') setDragActive(false);
  };

  const handleDrop = async (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    const files = [...(e.dataTransfer?.files || [])];
    if (files.length) await uploadFiles(files);
  };

  const handleFileInput = async (e) => {
    const files = [...(e.target?.files || [])];
    if (files.length) await uploadFiles(files);
    e.target.value = '';
  };

  const uploadFiles = async (files) => {
    setLoading(true);
    setError(null);
    const results = [];
    for (const file of files) {
      try {
        const fd = new FormData();
        fd.append('file', file);
        if (layer) fd.append('layer', layer);
        const r = await fetch(`${API_BASE}/documents/upload`, { method: 'POST', body: fd });
        if (!r.ok) throw new Error(await r.text());
        const result = await r.json();
        results.push({ file: file.name, success: true, result });
      } catch (err) {
        results.push({ file: file.name, success: false, error: err.message });
      }
    }
    setUploadedFiles(prev => [...results, ...prev]);
    setLoading(false);
    await loadIndexStatus();
  };

  const handleSearch = async () => {
    const query = searchQuery.trim();
    if (!query) { setSearchResults([]); return; }
    try {
      setLoading(true);
      setError(null);
      const r = await fetch(`${API_BASE}/documents/search`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query, limit: searchLimit }),
      });
      if (!r.ok) throw new Error(await r.text());
      const data = await r.json();
      setSearchResults(data.results || []);
    } catch (err) {
      setError(err.message);
      setSearchResults([]);
    } finally {
      setLoading(false);
    }
  };

  const toggleExpanded = (i) => setExpandedResult(expandedResult === i ? null : i);

  return (
    <div style={{ maxWidth: 1100, margin: '40px auto', padding: '0 24px', fontFamily: 'ui-sans-serif, system-ui' }}>
      <h1 style={{ fontSize: 28, fontWeight: 700, marginBottom: 32 }}>Upload &amp; Search</h1>

      {error && (
        <div style={{ marginBottom: 24, padding: 16, background: '#fff5f5', border: '1px solid #fca5a5', borderRadius: 8, color: '#b91c1c' }}>
          Error: {error}
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 24 }}>

        {/* Upload */}
        <div style={card}>
          <h2 style={{ fontSize: 18, fontWeight: 600, marginBottom: 16 }}>Upload Documents</h2>

          <div
            onDragEnter={handleDrag}
            onDragLeave={handleDrag}
            onDragOver={handleDrag}
            onDrop={handleDrop}
            style={{
              border: `2px dashed ${dragActive ? '#3b82f6' : '#d1d5db'}`,
              borderRadius: 8,
              padding: 24,
              textAlign: 'center',
              background: dragActive ? '#eff6ff' : '#fafafa',
              marginBottom: 16,
            }}
          >
            <p style={{ marginBottom: 8, color: '#4b5563' }}>Drop files here</p>
            <p style={{ fontSize: 13, color: '#9ca3af', marginBottom: 16 }}>PDF, DOCX, TXT, MD, Images</p>
            <label style={{ display: 'inline-block', padding: '8px 16px', background: '#3b82f6', color: '#fff', borderRadius: 8, cursor: 'pointer' }}>
              Choose Files
              <input type="file" multiple accept=".pdf,.docx,.txt,.md,.png,.jpg,.jpeg,.gif" onChange={handleFileInput} style={{ display: 'none' }} />
            </label>
          </div>

          <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 12 }}>
            <label style={{ fontSize: 13, color: '#4b5563' }}>Layer:</label>
            <select
              value={layer}
              onChange={e => setLayer(e.target.value)}
              style={{ flex: 1, padding: '6px 10px', border: '1px solid #d1d5db', borderRadius: 6, fontSize: 13 }}
            >
              <option value=''>(unscoped)</option>
              {layers.map(l => (
                <option key={l.name} value={l.name}>{l.name}</option>
              ))}
            </select>
          </div>

          {loading && (
            <div style={{ textAlign: 'center', color: '#3b82f6', marginBottom: 12 }}>Uploading...</div>
          )}

          {uploadedFiles.length > 0 && (
            <div>
              <p style={{ fontWeight: 500, marginBottom: 8 }}>Recent Uploads</p>
              <div style={{ maxHeight: 120, overflowY: 'auto' }}>
                {uploadedFiles.slice(0, 5).map((u, i) => (
                  <div key={i} style={{
                    fontSize: 13,
                    padding: '6px 10px',
                    borderRadius: 6,
                    marginBottom: 4,
                    background: u.success ? '#f0fdf4' : '#fff5f5',
                    color: u.success ? '#15803d' : '#b91c1c',
                  }}>
                    {u.success ? 'OK' : 'FAIL'}: {u.file}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Search */}
        <div style={card}>
          <h2 style={{ fontSize: 18, fontWeight: 600, marginBottom: 16 }}>Search Documents</h2>

          <input
            type="text"
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleSearch()}
            placeholder="Enter your search query..."
            style={{ width: '100%', padding: '8px 12px', border: '1px solid #d1d5db', borderRadius: 8, marginBottom: 10, boxSizing: 'border-box', fontSize: 14 }}
          />

          <div style={{ display: 'flex', gap: 8, marginBottom: 10 }}>
            <select
              value={searchLimit}
              onChange={e => setSearchLimit(parseInt(e.target.value))}
              style={{ padding: '8px 10px', border: '1px solid #d1d5db', borderRadius: 8 }}
            >
              <option value={3}>Top 3</option>
              <option value={5}>Top 5</option>
              <option value={10}>Top 10</option>
              <option value={20}>Top 20</option>
            </select>
            <button
              onClick={handleSearch}
              disabled={!searchQuery.trim() || loading}
              style={{ flex: 1, padding: '8px 14px', background: (!searchQuery.trim() || loading) ? '#d1d5db' : '#3b82f6', color: '#fff', border: 'none', borderRadius: 8, cursor: 'pointer', fontSize: 14 }}
            >
              Search
            </button>
          </div>

          {searchQuery && (
            <button
              onClick={() => { setSearchQuery(''); setSearchResults([]); }}
              style={{ width: '100%', padding: '8px 14px', border: '1px solid #d1d5db', borderRadius: 8, background: '#fff', cursor: 'pointer', marginBottom: 10 }}
            >
              Clear
            </button>
          )}

          {searchResults.length > 0 && (
            <div>
              <p style={{ fontWeight: 500, marginBottom: 8 }}>Results ({searchResults.length})</p>
              <div style={{ maxHeight: 360, overflowY: 'auto' }}>
                {searchResults.map((r, i) => (
                  <div key={i} style={{ border: '1px solid #e5e5e5', borderRadius: 8, padding: 12, marginBottom: 8 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                      <span style={{ fontWeight: 500, color: '#3b82f6', fontSize: 13 }}>{r.document_name}</span>
                      <span style={{ fontSize: 12, color: '#9ca3af' }}>{(r.similarity_score * 100).toFixed(1)}%</span>
                    </div>
                    <p style={{ fontSize: 13, color: '#4b5563', margin: 0 }}>
                      {(r.content || '').substring(0, 150)}{r.content?.length > 150 ? '...' : ''}
                    </p>
                    <button onClick={() => toggleExpanded(i)} style={{ fontSize: 12, color: '#3b82f6', background: 'none', border: 'none', cursor: 'pointer', padding: 0, marginTop: 6 }}>
                      {expandedResult === i ? 'Show less' : 'Show more'}
                    </button>
                    {expandedResult === i && (
                      <div style={{ marginTop: 8, padding: 8, background: '#f9fafb', borderRadius: 6, fontSize: 13 }}>{r.content}</div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Index Status */}
        <div style={card}>
          <h2 style={{ fontSize: 18, fontWeight: 600, marginBottom: 16 }}>Index Status</h2>

          {indexStatus ? (
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 10 }}>
                <span style={{ color: '#6b7280' }}>Documents:</span>
                <span style={{ fontWeight: 600 }}>{indexStatus.unique_documents ?? '—'}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 10 }}>
                <span style={{ color: '#6b7280' }}>Total chunks:</span>
                <span style={{ fontWeight: 600 }}>{indexStatus.total_chunks ?? '—'}</span>
              </div>

              {indexStatus.recent_documents?.length > 0 && (
                <div style={{ marginTop: 16 }}>
                  <p style={{ fontWeight: 500, marginBottom: 8, fontSize: 13 }}>Recent Documents</p>
                  <div style={{ maxHeight: 180, overflowY: 'auto' }}>
                    {indexStatus.recent_documents.map((d, i) => (
                      <div key={i} style={{ fontSize: 12, padding: '5px 8px', borderRadius: 6, marginBottom: 4, background: '#f9fafb' }}>
                        <span style={{ color: '#374151' }}>{d.name}</span>
                        <span style={{ color: '#9ca3af', marginLeft: 8 }}>{d.chunks} chunks</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <button
                onClick={loadIndexStatus}
                style={{ width: '100%', marginTop: 16, padding: '8px 14px', background: '#f3f4f6', border: '1px solid #e5e5e5', borderRadius: 8, cursor: 'pointer', fontSize: 13 }}
              >
                Refresh
              </button>
            </div>
          ) : (
            <div style={{ textAlign: 'center', color: '#9ca3af', paddingTop: 40 }}>
              Loading...
            </div>
          )}
        </div>

      </div>
    </div>
  );
}
