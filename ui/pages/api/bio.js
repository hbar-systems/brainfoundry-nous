// Bio card data (2026-11-06): who this brain is, in one read. Joins the api's public /identity with a
// one-word state from /health (only the status words, never endpoints or error text). Both upstream
// routes are already unauthenticated, so the card shows nothing a peer cannot already fetch.

async function getJson(path) {
  try {
    const r = await fetch(`http://api:8000${path}`, { cache: 'no-store' })
    if (!r.ok) return null
    return await r.json()
  } catch {
    return null
  }
}

export default async function handler(req, res) {
  const [identity, health] = await Promise.all([getJson('/identity'), getJson('/health')])
  if (!identity) return res.status(502).json({ error: 'the brain did not answer /identity' })

  const unset = (v) => (typeof v === 'string' && v.startsWith('${')) ? null : (v ?? null)
  const key = unset(identity.public_key)
  res.setHeader('Cache-Control', 'no-store')
  return res.status(200).json({
    name: unset(identity.display_name),
    brain_id: unset(identity.brain_id),
    role: identity.role || null,
    domain: identity.domain || null,
    tags: Array.isArray(identity.tags) ? identity.tags : [],
    model: identity.model || null,
    version: identity.version || null,
    public_key: key ? `${String(key).slice(0, 16)}...` : null,
    state: health ? {
      api: health.status || 'up',
      db: health.database?.status || health.db?.status || null,
      model: health.ollama?.status || null,
    } : null,
  })
}
