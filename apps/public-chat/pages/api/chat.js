// Server-side relay: browser → here → brain API /v1/public/chat.
// No API key forwarded. The brain endpoint authorizes by per-IP rate limit.
//
// Caps enforced before forwarding:
//   - max 10 messages in history (FIFO drop oldest)
//   - max 2000 estimated tokens across history+message (len/4 heuristic;
//     FIFO drop oldest until under cap)
//
// The brain endpoint streams tokens as Server-Sent Events. This relay
// inspects the upstream Content-Type:
//   - text/event-stream → pass the stream through unmodified to the browser
//   - application/json (errors, rate-limit, etc.) → forward status + JSON

const MAX_HISTORY = 10
const MAX_TOKENS_EST = 2000
const MAX_MESSAGE_CHARS = 4000

const estimateTokens = (text) => Math.ceil((text || '').length / 4)

const capHistory = (history, currentMessage) => {
  let trimmed = Array.isArray(history) ? history.filter((m) =>
    m && (m.role === 'user' || m.role === 'assistant') && typeof m.content === 'string'
  ) : []

  if (trimmed.length > MAX_HISTORY) trimmed = trimmed.slice(-MAX_HISTORY)

  let total = estimateTokens(currentMessage) + trimmed.reduce((s, m) => s + estimateTokens(m.content), 0)
  while (total > MAX_TOKENS_EST && trimmed.length > 0) {
    const dropped = trimmed.shift()
    total -= estimateTokens(dropped.content)
  }
  return trimmed
}

// Disable Next.js's default response size cap so the SSE body can run as
// long as the model takes (well past Next.js's 4MB default).
export const config = {
  api: {
    responseLimit: false,
  },
}

export default async function handler(req, res) {
  if (req.method !== 'POST') {
    res.setHeader('Allow', 'POST')
    return res.status(405).json({ error: 'Method not allowed' })
  }

  const apiUrl = process.env.API_INTERNAL_URL
  if (!apiUrl) {
    return res.status(500).json({ error: 'Server misconfigured: API_INTERNAL_URL not set' })
  }

  let body
  try {
    body = req.body && typeof req.body === 'object' ? req.body : JSON.parse(req.body || '{}')
  } catch {
    return res.status(400).json({ error: 'Invalid JSON' })
  }

  const message = typeof body.message === 'string' ? body.message.trim() : ''
  if (!message) return res.status(400).json({ error: 'message is required' })
  if (message.length > MAX_MESSAGE_CHARS) {
    return res.status(400).json({ error: `message too long (max ${MAX_MESSAGE_CHARS} chars)` })
  }

  const history = capHistory(body.history, message)

  // Forward client IP via X-Forwarded-For so the brain endpoint can rate-limit per-IP.
  // Caddy already appends the real client IP; this header just relays whatever
  // Next.js received. The brain reads the LAST hop, not the first.
  const xff = req.headers['x-forwarded-for'] || ''

  let upstream
  try {
    upstream = await fetch(`${apiUrl}/v1/public/chat`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'text/event-stream',
        ...(xff ? { 'X-Forwarded-For': xff } : {}),
      },
      body: JSON.stringify({ message, history }),
    })
  } catch (e) {
    return res.status(502).json({ error: `Upstream unreachable: ${e.message}` })
  }

  const upstreamCT = upstream.headers.get('content-type') || ''

  // Non-stream upstream response (errors, rate limit). Forward as JSON.
  if (!upstreamCT.includes('text/event-stream')) {
    const data = await upstream.json().catch(() => ({}))
    if (upstream.status === 429) {
      return res.status(429).json({ error: data?.error || 'Rate limited. Please wait a minute.' })
    }
    if (!upstream.ok) {
      return res.status(upstream.status).json({ error: data?.error || data?.detail || `Upstream error ${upstream.status}` })
    }
    // 200 with non-SSE body (shouldn't happen post-streaming switch, but
    // tolerate it gracefully).
    return res.status(200).json(data)
  }

  // SSE pass-through. Set headers, then pipe chunks as they arrive.
  res.writeHead(200, {
    'Content-Type': 'text/event-stream',
    'Cache-Control': 'no-cache, no-transform',
    Connection: 'keep-alive',
    'X-Accel-Buffering': 'no',
  })
  if (typeof res.flushHeaders === 'function') res.flushHeaders()

  const reader = upstream.body.getReader()
  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      res.write(Buffer.from(value))
      if (typeof res.flush === 'function') res.flush()
    }
  } catch (e) {
    // Surface a final SSE error event so the client doesn't sit waiting.
    try {
      res.write(`data: ${JSON.stringify({ error: `Stream interrupted: ${e.message}` })}\n\n`)
    } catch {}
  } finally {
    res.end()
  }
}
