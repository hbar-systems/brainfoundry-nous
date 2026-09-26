import Head from 'next/head'
import { useEffect, useState } from 'react'

// System: the technical surface of the box (2026-09-24). Disk, memory, load, containers,
// backups, last update and the database from the api (GET /admin/system); the tailnet,
// connections, failed services and the bridge's units from the bridge on the host
// (GET /cc/system) when CC is on. Every tile carries its level; the reasons are listed.
const mono = { fontFamily: "'JetBrains Mono', ui-monospace, monospace" }
const T = { ink: 'var(--text)', dim: 'var(--text-dim, #9a8f82)', faint: 'var(--text-faint, #6b5f52)', line: 'var(--line, #2a2621)', card: 'var(--card, #16140f)', gold: 'var(--accent, #c9a96e)', ok: '#7fc99c', warn: '#d4b86a', alert: '#d49a9a' }
const tone = (l) => (l === 'alert' ? T.alert : l === 'warn' ? T.warn : l === 'ok' ? T.ok : T.faint)

function Tile({ label, level, value, sub }) {
  return (
    <div style={{ border: `1px solid ${T.line}`, borderRadius: '10px', backgroundColor: T.card, padding: '12px 14px', minWidth: '150px', flex: '1 1 150px' }}>
      <p style={{ ...mono, fontSize: '10px', letterSpacing: '0.15em', textTransform: 'uppercase', color: tone(level), margin: '0 0 6px 0' }}>{label}{level ? ` · ${level}` : ''}</p>
      <p style={{ margin: 0, fontSize: '20px', color: T.ink }}>{value}</p>
      {sub ? <p style={{ ...mono, margin: '4px 0 0 0', fontSize: '11px', color: T.dim }}>{sub}</p> : null}
    </div>
  )
}

export default function System() {
  const [api, setApi] = useState(null)
  const [host, setHost] = useState(null)
  const [health, setHealth] = useState(null)
  const [at, setAt] = useState(null)
  const [pruning, setPruning] = useState(null)
  const load = async () => {
    try { const r = await fetch('/api/bf/admin/system', { cache: 'no-store' }); setApi(r.ok ? await r.json() : { error: `api ${r.status}` }) } catch { setApi({ error: 'api not answering' }) }
    try { const r = await fetch('/cc/system', { cache: 'no-store' }); setHost(r.ok ? await r.json() : null) } catch { setHost(null) }
    try { const r = await fetch('/api/bf/health', { cache: 'no-store' }); setHealth(r.ok ? await r.json() : null) } catch { setHealth(null) }
    setAt(new Date())
  }
  useEffect(() => { load(); const t = setInterval(load, 60000); return () => clearInterval(t) }, [])
  const h = (api && api.host) || {}
  const dk = (api && api.docker) || {}
  const b = (api && api.backups) || {}
  const up = (api && api.update) || {}
  const db = (api && api.database) || {}
  const ol = (health && health.services && health.services.ollama) || {}
  const em = (health && health.services && health.services.embeddings && health.services.embeddings.spoke) || null
  const warnings = [...((api && api.warnings) || []), ...((host && host.warnings) || [])]
  return (
    <>
      <Head><title>System · BrainFoundry</title></Head>
      <div style={{ maxWidth: '980px', margin: '0 auto', padding: '18px 20px 60px', color: T.ink, fontFamily: 'var(--font-display, serif)' }}>
        <p style={{ ...mono, fontSize: '11px', letterSpacing: '0.15em', textTransform: 'uppercase', color: T.gold, margin: '0 0 6px 0' }}>System · the box in numbers</p>
        <p style={{ fontSize: '13px', color: T.dim, margin: '0 0 16px 0' }}>
          {api && api.level ? <span style={{ color: tone(api.level) }}>{api.level === 'ok' ? 'everything within thresholds' : `${api.level}`}</span> : null}
          {warnings.length ? <span> · {warnings.join(' · ')}</span> : null}
          {at ? <span style={{ ...mono, fontSize: '11px', color: T.faint }}> · read {at.toLocaleTimeString()} · refreshes every minute</span> : null}
        </p>
        {api && api.error ? <p style={{ color: T.alert, fontSize: '13px' }}>{api.error}</p> : null}

        <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap', marginBottom: '18px' }}>
          {h.disk && !h.disk.error ? <Tile label="disk" level={h.disk.level} value={`${h.disk.pct}%`} sub={`${h.disk.used_gb} of ${h.disk.total_gb} GB used, ${h.disk.free_gb} free`} /> : null}
          {h.memory ? <Tile label="memory" level={h.memory.level} value={`${h.memory.available_gb} GB free`} sub={`of ${h.memory.total_gb} GB (${h.memory.available_pct}% available)`} /> : null}
          {h.load ? <Tile label="load" level={h.load.level} value={h.load.five} sub={`1 min ${h.load.one} · 15 min ${h.load.fifteen} · ${h.load.cores} cores`} /> : null}
          {typeof h.uptime_days === 'number' ? <Tile label="uptime" value={`${h.uptime_days} d`} /> : null}
          {b.count !== undefined ? <Tile label="backups" level={b.level} value={b.count ? `${b.age_days} d ago` : 'none'} sub={b.count ? `${b.count} kept, ${b.size_gb} GB, latest ${b.latest}` : b.dir} /> : null}
          {db.documents !== undefined ? <Tile label="memory store" level={db.level} value={`${db.documents} docs`} sub={`${db.chunks} chunks · ${db.size_gb} GB in Postgres`} /> : (db.error ? <Tile label="memory store" level="warn" value="?" sub={db.error} /> : null)}
        </div>

        <h2 style={{ fontWeight: 'normal', fontSize: '15px', color: T.gold, margin: '18px 0 8px 0' }}>Containers and images</h2>
        <div style={{ ...mono, fontSize: '12px', color: T.dim, lineHeight: 1.7 }}>
          {(dk.containers || []).map(c => <div key={c.name}><span style={{ color: c.state === 'running' ? T.ok : T.alert }}>{c.state}</span> {c.name} <span style={{ color: T.faint }}>{c.status} · {c.image}</span></div>)}
          {dk.images ? <div style={{ marginTop: '6px' }}>{dk.images.count} images, {dk.images.size}{typeof dk.reclaimable_gb === 'number' ? ` · ${dk.reclaimable_gb} GB reclaimable` : ''}
            {dk.reclaimable_gb >= 1 ? <> · <a onClick={async () => { setPruning('working'); try { const r = await fetch('/api/bf/admin/prune-images', { method: 'POST' }); const d = await r.json().catch(() => ({})); setPruning(d.result || (r.ok ? 'done' : 'failed')) } catch { setPruning('failed') } load() }} style={{ color: T.gold, cursor: 'pointer', textDecoration: 'underline' }}>reclaim now</a>{pruning ? ` (${pruning})` : ''}</> : null}</div> : null}
          <div>running commit {up.running_commit}{up.previous_commit ? ` · previous ${up.previous_commit}` : ''}{up.built_at ? ` · built ${up.built_at}` : ''}{up.helper_log_at ? ` · last update ${up.helper_log_at.slice(0, 16).replace('T', ' ')}` : ''}</div>
        </div>

        <h2 style={{ fontWeight: 'normal', fontSize: '15px', color: T.gold, margin: '18px 0 8px 0' }}>Reasoner and spokes</h2>
        <div style={{ ...mono, fontSize: '12px', color: T.dim, lineHeight: 1.7 }}>
          <div>local inference: {ol.endpoint || '?'}{ol.spoke ? ` · spoke ${ol.spoke} ${ol.spoke_up ? 'answering' : 'not answering, box in use'}` : ' · no spoke set'}{typeof ol.models === 'number' ? ` · ${ol.models} models` : ''}</div>
          {em ? <div>embeddings: {em.on ? (em.serving ? `on the spoke (${em.model})` : em.url ? 'spoke not serving the model, in-process' : 'in-process') : 'in-process (spoke off)'}{em.texts_embedded_there ? ` · ${em.texts_embedded_there} texts there, ${em.texts_fell_back} fell back` : ''}</div> : null}
        </div>

        {host ? (
          <>
            <h2 style={{ fontWeight: 'normal', fontSize: '15px', color: T.gold, margin: '18px 0 8px 0' }}>Host, from the bridge</h2>
            <div style={{ ...mono, fontSize: '12px', color: T.dim, lineHeight: 1.7 }}>
              {host.tailnet ? <div>tailnet: {host.tailnet.self} {host.tailnet.ip} ({host.tailnet.state}) · peers: {(host.tailnet.peers || []).map(p => <span key={p.name} style={{ color: p.online ? T.ink : T.faint }}>{p.name} {p.ip}{p.online ? '' : ' (offline)'}; </span>)}</div> : <div>tailnet: not joined</div>}
              {host.connections ? <div>connections: {host.connections.established} established · listening on {(host.connections.listening_ports || []).join(', ')}</div> : null}
              <div>failed services: {host.failed_units && host.failed_units.length ? <span style={{ color: T.alert }}>{host.failed_units.join(', ')}</span> : 'none'}</div>
              <div>units: {Object.entries(host.units || {}).map(([k, v]) => <span key={k} style={{ color: v === 'active' ? T.ink : T.warn }}>{k} {v}; </span>)}</div>
              <div>permits recorded {host.permits} · judgments {host.judgments} · jobs running {host.jobs_running}</div>
            </div>
          </>
        ) : null}
        <p style={{ ...mono, fontSize: '11px', color: T.faint, margin: '22px 0 0 0' }}>thresholds: disk 80/90% · memory available 15/7% · load 1.0/2.0 per core · backup age 2/7 days · reclaimable docker 5 GB. The only action here is "reclaim now": it removes images no container uses, the same step the update runs.</p>
      </div>
    </>
  )
}
