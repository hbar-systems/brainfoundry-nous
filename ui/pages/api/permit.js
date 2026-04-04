export default async function handler(req, res) {
  if (req.method !== 'POST') return res.status(405).end()

  try {
    const r = await fetch('http://nodeos:8001/v1/loops/request', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        node_id: process.env.BRAIN_ID || process.env.BRAIN_NODE_ID || 'my-brain-01',
        agent_id: 'console',
        loop_type: 'chat',
        ttl_seconds: 300,
        reason: 'console chat session',
      }),
    })

    const data = await r.json()

    if (!r.ok) {
      return res.status(502).json({ error: 'permit request failed', detail: data })
    }

    return res.status(200).json({ permit_id: data.permit_id })
  } catch (e) {
    return res.status(502).json({ error: String(e) })
  }
}
