// ui/pages/api/bf/[...path].js
export default async function handler(req, res) {
  const base = process.env.API_INTERNAL_URL || "http://api:8000";
  const pathParts = req.query.path || [];
  const path = Array.isArray(pathParts) ? pathParts.join("/") : String(pathParts);

  const url = `${base.replace(/\/$/, "")}/${path}`;

  try {
    const headers = {};
    // forward content-type when present
    if (req.headers["content-type"]) headers["content-type"] = req.headers["content-type"];
    // inject server-side API key (falls back to browser-forwarded header)
    const apiKey = process.env.BRAIN_API_KEY || req.headers["x-api-key"] || "";
    if (apiKey) headers["x-api-key"] = apiKey;
    if (req.headers["authorization"]) headers["authorization"] = req.headers["authorization"];

    const r = await fetch(url, {
      method: req.method,
      headers,
      body: req.method === "GET" || req.method === "HEAD" ? undefined : JSON.stringify(req.body),
    });

    const text = await r.text();
    res.status(r.status);

    // try to keep JSON responses as JSON
    const ct = r.headers.get("content-type") || "";
    if (ct.includes("application/json")) {
      res.setHeader("content-type", "application/json");
      return res.send(text);
    }

    res.setHeader("content-type", ct || "text/plain");
    return res.send(text);
  } catch (e) {
    return res.status(502).json({ error: String(e) });
  }
}
