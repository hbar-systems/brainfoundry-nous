import Head from 'next/head'
import { useEffect, useState } from 'react'

const COLORS = {
  bg: '#0e0c0b',
  surface: '#161310',
  surface2: '#1c1814',
  text: '#e8e0d5',
  muted: '#6b5f52',
  accent: '#c9a96e',
  border: '#2a2420',
  dim: '#4a3f36',
}

function fmtDate(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
}

function fmtRelative(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  const diff = Math.floor((Date.now() - d.getTime()) / 60000)
  if (diff < 1) return 'just now'
  if (diff < 60) return `${diff}m ago`
  if (diff < 1440) return `${Math.floor(diff / 60)}h ago`
  if (diff < 1440 * 30) return `${Math.floor(diff / 1440)}d ago`
  return d.toLocaleDateString()
}

function fmtNumber(n) {
  if (n === null || n === undefined) return '—'
  return n.toLocaleString()
}

function StatCard({ label, value, sub }) {
  return (
    <div style={{
      backgroundColor: COLORS.surface,
      border: `1px solid ${COLORS.border}`,
      borderRadius: '10px',
      padding: '20px 22px',
    }}>
      <div style={{
        fontSize: '10px',
        color: COLORS.muted,
        marginBottom: '8px',
        textTransform: 'uppercase',
        letterSpacing: '0.12em',
        fontFamily: 'DM Mono, monospace',
      }}>
        {label}
      </div>
      <div style={{
        fontSize: '28px',
        fontFamily: 'Lora, ui-serif, serif',
        fontWeight: 600,
        color: COLORS.text,
        marginBottom: sub ? '4px' : 0,
        lineHeight: 1.1,
      }}>
        {value}
      </div>
      {sub && (
        <div style={{ fontSize: '12px', color: COLORS.muted, fontFamily: 'DM Mono, monospace' }}>
          {sub}
        </div>
      )}
    </div>
  )
}

function SectionTitle({ children, sub }) {
  return (
    <div style={{ marginBottom: '14px' }}>
      <h2 style={{
        fontFamily: 'Lora, ui-serif, serif',
        fontSize: '18px',
        color: COLORS.text,
        margin: 0,
        fontWeight: 600,
      }}>
        {children}
      </h2>
      {sub && (
        <p style={{ color: COLORS.muted, fontSize: '12px', margin: '4px 0 0 0' }}>
          {sub}
        </p>
      )}
    </div>
  )
}

function Bar({ value, max, color }) {
  const pct = max > 0 ? Math.max(2, Math.round((value / max) * 100)) : 0
  return (
    <div style={{
      height: '6px',
      width: '100%',
      background: COLORS.surface,
      borderRadius: '3px',
      overflow: 'hidden',
    }}>
      <div style={{
        height: '100%',
        width: `${pct}%`,
        background: color || COLORS.accent,
        opacity: 0.85,
      }} />
    </div>
  )
}

export default function Trace() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    fetch('/api/bf/admin/trace')
      .then(async r => {
        if (!r.ok) {
          const text = await r.text()
          throw new Error(`${r.status}: ${text.slice(0, 200)}`)
        }
        return r.json()
      })
      .then(d => { setData(d); setLoading(false) })
      .catch(e => { setError(e.message); setLoading(false) })
  }, [])

  const layerMaxChunks = data?.documents?.by_layer?.length
    ? Math.max(...data.documents.by_layer.map(l => l.chunk_count || 0))
    : 0
  const topicMax = data?.topics?.length
    ? Math.max(...data.topics.map(t => t.count || 0))
    : 0

  return (
    <>
      <Head><title>Trace · BrainFoundry</title></Head>
      <div style={{
        padding: '40px 32px',
        maxWidth: '960px',
        margin: '0 auto',
        fontFamily: 'Lora, ui-serif, serif',
      }}>
        <p style={{
          color: COLORS.accent,
          fontSize: '11px',
          letterSpacing: '0.15em',
          textTransform: 'uppercase',
          fontFamily: 'DM Mono, monospace',
          margin: '0 0 6px 0',
        }}>
          brainfoundry-nous · trace
        </p>
        <h1 style={{
          fontSize: '32px',
          color: COLORS.text,
          margin: '0 0 6px 0',
          fontWeight: 600,
        }}>
          Your trace
        </h1>
        <p style={{ color: COLORS.muted, fontSize: '14px', margin: '0 0 32px 0', lineHeight: 1.6 }}>
          What your brain has tracked about you, made visible. Aggregated only —
          no message content is exposed verbatim.
        </p>

        {loading && (
          <p style={{ color: COLORS.muted, fontSize: '13px', fontStyle: 'italic' }}>
            Loading trace…
          </p>
        )}

        {error && (
          <div style={{
            padding: '12px 14px',
            background: '#3a1e1e',
            color: '#c98080',
            borderRadius: '6px',
            fontSize: '12px',
            fontFamily: 'DM Mono, monospace',
          }}>
            Failed to load: {error}
          </div>
        )}

        {data && (
          <>
            {/* Brain born on */}
            <div style={{
              padding: '18px 22px',
              background: COLORS.surface,
              border: `1px solid ${COLORS.border}`,
              borderRadius: '10px',
              marginBottom: '28px',
            }}>
              <div style={{
                fontSize: '10px',
                color: COLORS.muted,
                letterSpacing: '0.12em',
                textTransform: 'uppercase',
                fontFamily: 'DM Mono, monospace',
                marginBottom: '6px',
              }}>
                Brain born on
              </div>
              <div style={{
                fontFamily: 'Lora, ui-serif, serif',
                fontSize: '22px',
                color: COLORS.text,
                fontWeight: 600,
              }}>
                {fmtDate(data.born_on)}
              </div>
              {data.brain_id && (
                <div style={{
                  fontSize: '11px',
                  color: COLORS.dim,
                  fontFamily: 'DM Mono, monospace',
                  marginTop: '6px',
                }}>
                  {data.brain_id}
                </div>
              )}
            </div>

            {/* Top stat row */}
            <div style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
              gap: '14px',
              marginBottom: '36px',
            }}>
              <StatCard
                label="Chat sessions"
                value={fmtNumber(data.chat?.total_sessions)}
                sub={data.chat?.last_message_at ? `last · ${fmtRelative(data.chat.last_message_at)}` : null}
              />
              <StatCard
                label="Chat messages"
                value={fmtNumber(data.chat?.total_messages)}
                sub="user + assistant turns"
              />
              <StatCard
                label="Documents"
                value={fmtNumber(data.documents?.unique_documents)}
                sub={`${fmtNumber(data.documents?.total_chunks)} chunks`}
              />
              <StatCard
                label="Federation"
                value={fmtNumber((data.federation?.sent || 0) + (data.federation?.received || 0))}
                sub={`${data.federation?.sent || 0} sent · ${data.federation?.received || 0} received`}
              />
            </div>

            {/* Knowledge by layer */}
            <div style={{ marginBottom: '36px' }}>
              <SectionTitle sub="How your knowledge is distributed across memory layers.">
                Knowledge by layer
              </SectionTitle>
              {(!data.documents?.by_layer || data.documents.by_layer.length === 0) ? (
                <p style={{ color: COLORS.muted, fontSize: '13px', fontStyle: 'italic' }}>
                  No documents ingested yet.
                </p>
              ) : (
                <div style={{
                  background: COLORS.surface,
                  border: `1px solid ${COLORS.border}`,
                  borderRadius: '10px',
                  padding: '18px 22px',
                }}>
                  {data.documents.by_layer.map(l => (
                    <div key={l.layer || '_unscoped'} style={{ marginBottom: '14px' }}>
                      <div style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'baseline',
                        marginBottom: '6px',
                      }}>
                        <span style={{
                          color: l.layer ? COLORS.text : COLORS.muted,
                          fontFamily: 'DM Mono, monospace',
                          fontSize: '13px',
                        }}>
                          {l.layer || '(unscoped)'}
                        </span>
                        <span style={{
                          color: COLORS.muted,
                          fontFamily: 'DM Mono, monospace',
                          fontSize: '11px',
                        }}>
                          {l.doc_count} docs · {l.chunk_count} chunks
                        </span>
                      </div>
                      <Bar value={l.chunk_count} max={layerMaxChunks} />
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Top topics */}
            <div style={{ marginBottom: '36px' }}>
              <SectionTitle sub="Most frequent terms across your recent chat (last 2,000 messages, stopwords removed).">
                Top topics
              </SectionTitle>
              {(!data.topics || data.topics.length === 0) ? (
                <p style={{ color: COLORS.muted, fontSize: '13px', fontStyle: 'italic' }}>
                  Not enough chat yet to surface topics.
                </p>
              ) : (
                <div style={{
                  background: COLORS.surface,
                  border: `1px solid ${COLORS.border}`,
                  borderRadius: '10px',
                  padding: '18px 22px',
                }}>
                  {data.topics.map(t => (
                    <div key={t.term} style={{ marginBottom: '12px' }}>
                      <div style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'baseline',
                        marginBottom: '4px',
                      }}>
                        <span style={{
                          color: COLORS.text,
                          fontFamily: 'DM Mono, monospace',
                          fontSize: '13px',
                        }}>
                          {t.term}
                        </span>
                        <span style={{
                          color: COLORS.muted,
                          fontFamily: 'DM Mono, monospace',
                          fontSize: '11px',
                        }}>
                          {t.count}
                        </span>
                      </div>
                      <Bar value={t.count} max={topicMax} />
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Recent ingestion timeline */}
            <div style={{ marginBottom: '36px' }}>
              <SectionTitle sub="The last 20 documents your brain ingested.">
                Recent ingestion
              </SectionTitle>
              {(!data.documents?.recent || data.documents.recent.length === 0) ? (
                <p style={{ color: COLORS.muted, fontSize: '13px', fontStyle: 'italic' }}>
                  No ingestion history yet.
                </p>
              ) : (
                <div style={{
                  background: COLORS.surface,
                  border: `1px solid ${COLORS.border}`,
                  borderRadius: '10px',
                  overflow: 'hidden',
                }}>
                  {data.documents.recent.map((doc, i) => (
                    <div
                      key={doc.document_name + i}
                      style={{
                        padding: '12px 22px',
                        borderBottom: i === data.documents.recent.length - 1 ? 'none' : `1px solid ${COLORS.border}`,
                        display: 'flex',
                        alignItems: 'baseline',
                        gap: '16px',
                      }}
                    >
                      <span style={{
                        color: COLORS.text,
                        fontFamily: 'DM Mono, monospace',
                        fontSize: '12px',
                        flex: 1,
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                      }}>
                        {doc.document_name}
                      </span>
                      {doc.layer && (
                        <span style={{
                          color: COLORS.accent,
                          fontFamily: 'DM Mono, monospace',
                          fontSize: '10px',
                          letterSpacing: '0.08em',
                          textTransform: 'uppercase',
                        }}>
                          {doc.layer}
                        </span>
                      )}
                      <span style={{
                        color: COLORS.muted,
                        fontFamily: 'DM Mono, monospace',
                        fontSize: '11px',
                        minWidth: '70px',
                        textAlign: 'right',
                      }}>
                        {doc.chunks} chunks
                      </span>
                      <span style={{
                        color: COLORS.dim,
                        fontFamily: 'DM Mono, monospace',
                        fontSize: '11px',
                        minWidth: '90px',
                        textAlign: 'right',
                      }}>
                        {fmtRelative(doc.ingested_at)}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <p style={{
              color: COLORS.dim,
              fontSize: '11px',
              fontFamily: 'DM Mono, monospace',
              textAlign: 'center',
              marginTop: '40px',
            }}>
              spirit-cousin to hbar.you · operator&rsquo;s own corpus made visible
            </p>
          </>
        )}
      </div>
    </>
  )
}
