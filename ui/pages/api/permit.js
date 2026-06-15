export default async function handler(req, res) {
  if (req.method !== 'POST') return res.status(405).end()

  try {
    // Optional caller attribution. Callers with no body (console chat,
    // upload) keep the historical 'console' defaults. The brain-app bridge
    // passes agent_id 'app:<id>' so app-originated permits are attributable
    // in the NodeOS / BrainKernel audit trail.
    const opts = (req.body && typeof req.body === 'object') ? req.body : {}

    const headers = { 'Content-Type': 'application/json' }
    if (process.env.NODEOS_INTERNAL_KEY) {
      headers['X-Internal-Key'] = process.env.NODEOS_INTERNAL_KEY
    }
    const r = await fetch('http://nodeos:8001/v1/loops/request', {
      method: 'POST',
      headers,
      body: JSON.stringify({
        node_id: process.env.BRAIN_ID || process.env.BRAIN_NODE_ID || 'my-brain-01',
        agent_id: opts.agent_id || 'console',
        loop_type: opts.loop_type || 'chat',
        ttl_seconds: 300,
        reason: opts.reason || 'console chat session',
      }),
    })

    const data = await r.json()

    if (!r.ok) {
      return res.status(502).json({ error: 'permit request failed', detail: data })
    }

    return res.status(200).json({
      permit_id: data.permit_id,
      permit_token: data.permit_token,
    })
  } catch (e) {
    return res.status(502).json({ error: String(e) })
  }
}
