import { useEffect, useState } from 'react'
import { fetchTags, fetchDocsByTags, freeTextSearch } from '../lib/brain'

export default function Docs() {
  const [tags, setTags] = useState([])
  const [selectedTags, setSelectedTags] = useState([])
  const [docs, setDocs] = useState([])
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [searching, setSearching] = useState(false)
  const [loading, setLoading] = useState(true)
  const [tagsError, setTagsError] = useState(null)

  useEffect(() => {
    fetchTags()
      .then(setTags)
      .catch(e => setTagsError(e.message))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    if (selectedTags.length === 0) { setDocs([]); return }
    fetchDocsByTags(selectedTags).then(setDocs).catch(console.error)
  }, [selectedTags])

  const toggleTag = name => {
    setSelectedTags(prev =>
      prev.includes(name) ? prev.filter(t => t !== name) : [...prev, name]
    )
  }

  const doSearch = async () => {
    if (!query.trim()) return
    setSearching(true)
    setResults([])
    try {
      const r = await freeTextSearch(query.trim())
      setResults(r)
    } catch (e) {
      console.error(e)
    } finally {
      setSearching(false)
    }
  }

  return (
    <div style={{ padding: '40px 32px', maxWidth: '920px', margin: '0 auto' }}>

      <div style={{ marginBottom: '32px' }}>
        <h1 style={{ fontSize: '26px', fontWeight: '700', margin: '0 0 6px 0', color: '#e5e5e5' }}>
          Knowledge Base
        </h1>
        <p style={{ color: '#444', fontSize: '13px', margin: 0 }}>
          RAG knowledge base &middot; 384-dim embeddings
        </p>
      </div>

      {/* Search */}
      <div style={{ display: 'flex', gap: '10px', marginBottom: '36px' }}>
        <input
          value={query}
          onChange={e => setQuery(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && doSearch()}
          placeholder="Semantic search across all documents..."
          style={{
            flex: 1,
            padding: '12px 16px',
            backgroundColor: '#111',
            border: '1px solid #1e1e1e',
            borderRadius: '8px',
            color: '#e5e5e5',
            fontSize: '14px',
            outline: 'none',
            transition: 'border-color 0.15s ease',
          }}
          onFocus={e => e.target.style.borderColor = '#667eea60'}
          onBlur={e => e.target.style.borderColor = '#1e1e1e'}
        />
        <button
          onClick={doSearch}
          disabled={searching || !query.trim()}
          style={{
            padding: '12px 20px',
            borderRadius: '8px',
            border: 'none',
            cursor: searching || !query.trim() ? 'not-allowed' : 'pointer',
            fontSize: '14px',
            fontWeight: '600',
            background: '#e5e5e5',
            color: '#0a0a0a',
            opacity: searching || !query.trim() ? 0.4 : 1,
            transition: 'opacity 0.15s ease',
          }}
        >
          {searching ? '...' : 'Search'}
        </button>
      </div>

      {/* Search results */}
      {results.length > 0 && (
        <div style={{ marginBottom: '40px' }}>
          <div style={{ fontSize: '12px', color: '#444', marginBottom: '12px', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
            {results.length} results
          </div>
          {results.map((r, i) => (
            <div key={i} style={{
              backgroundColor: '#111',
              border: '1px solid #1e1e1e',
              borderRadius: '10px',
              padding: '16px',
              marginBottom: '8px',
            }}>
              <div style={{ fontSize: '12px', color: '#667eea', marginBottom: '8px', fontWeight: '500' }}>
                {r.document || r.filename || r.source || `Result ${i + 1}`}
              </div>
              <div style={{ fontSize: '13px', color: '#999', lineHeight: '1.6' }}>
                {r.content || r.text || r.chunk || ''}
              </div>
              {r.score !== undefined && (
                <div style={{ fontSize: '11px', color: '#333', marginTop: '8px' }}>
                  score: {r.score?.toFixed(4)}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Tags */}
      <div>
        <div style={{ fontSize: '12px', color: '#444', marginBottom: '12px', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
          {loading ? 'Loading...' : tagsError ? 'Tag index unavailable' : `${tags.length} tags`}
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', marginBottom: '24px' }}>
          {tags.map(t => {
            const name = typeof t === 'string' ? t : t.name
            const count = typeof t === 'object' ? t.count : null
            const active = selectedTags.includes(name)
            return (
              <button
                key={name}
                onClick={() => toggleTag(name)}
                style={{
                  padding: '5px 12px',
                  borderRadius: '6px',
                  border: `1px solid ${active ? '#667eea' : '#1e1e1e'}`,
                  backgroundColor: active ? '#667eea15' : '#111',
                  color: active ? '#667eea' : '#555',
                  fontSize: '13px',
                  cursor: 'pointer',
                  transition: 'all 0.15s ease',
                }}
              >
                {name}{count ? ` · ${count}` : ''}
              </button>
            )
          })}
        </div>

        {docs.length > 0 && (
          <div>
            <div style={{ fontSize: '12px', color: '#444', marginBottom: '12px', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
              {docs.length} documents
            </div>
            {docs.map((d, i) => (
              <div key={i} style={{
                backgroundColor: '#111',
                border: '1px solid #1e1e1e',
                borderRadius: '8px',
                padding: '12px 16px',
                marginBottom: '6px',
                fontSize: '13px',
                color: '#777',
              }}>
                {typeof d === 'string' ? d : (d.document || d.filename || JSON.stringify(d))}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
