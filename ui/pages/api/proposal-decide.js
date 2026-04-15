export default async function handler(req, res) {
  if (req.method !== 'POST') return res.status(405).end()

  try {
    const { proposal_id, decision, decided_by, note } = req.body || {}
    if (!proposal_id) return res.status(400).json({ error: 'proposal_id required' })
    if (!decision || !['APPROVE', 'DENY'].includes(decision)) {
      return res.status(400).json({ error: 'decision must be APPROVE or DENY' })
    }

    const headers = { 'Content-Type': 'application/json' }
    if (process.env.NODEOS_INTERNAL_KEY) headers['X-Internal-Key'] = process.env.NODEOS_INTERNAL_KEY

    const r = await fetch(`http://nodeos:8001/v1/memory/${encodeURIComponent(proposal_id)}/decide`, {
      method: 'POST',
      headers,
      body: JSON.stringify({
        decision,
        decided_by: decided_by || 'operator',
        note: note || null,
      }),
    })

    const data = await r.json().catch(() => ({}))
    if (!r.ok) return res.status(502).json({ error: 'decide failed', detail: data })
    return res.status(200).json(data)
  } catch (e) {
    return res.status(502).json({ error: String(e) })
  }
}
