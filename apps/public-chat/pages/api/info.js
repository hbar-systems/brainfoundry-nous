// Relay for the page's name and AI label: brain API /v1/public/info (no key, public).
export default async function handler(req, res) {
  const apiUrl = process.env.API_INTERNAL_URL
  if (!apiUrl) return res.status(200).json({ name: '', label: '' })
  try {
    const r = await fetch(`${apiUrl}/v1/public/info`)
    const j = r.ok ? await r.json() : {}
    return res.status(200).json({ name: j.name || '', label: j.label || '' })
  } catch {
    return res.status(200).json({ name: '', label: '' })
  }
}
