// ui/pages/api/nodeos/[...path].js
// Proxy for NodeOS authority service (internal docker network only)
// AUTHORITY PROTECTION: Block /v1/memory/{id}/decide endpoint
export default async function handler(req, res) {
  const base = process.env.NODEOS_INTERNAL_URL || "http://nodeos:8001";
  const pathParts = req.query.path || [];
  const path = Array.isArray(pathParts) ? pathParts.join("/") : String(pathParts);

  // DENYLIST: Block memory decision endpoint (authority-only)
  if (path.startsWith("v1/memory/") && path.endsWith("/decide")) {
    return res.status(404).json({ error: "Not found" });
  }

  const url = `${base.replace(/\/$/, "")}/${path}`;

  try {
    const headers = {};
    // Forward content-type when present
    if (req.headers["content-type"]) {
      headers["content-type"] = req.headers["content-type"];
    }

    const r = await fetch(url, {
      method: req.method,
      headers,
      body: req.method === "GET" || req.method === "HEAD" ? undefined : JSON.stringify(req.body),
    });

    const text = await r.text();
    res.status(r.status);

    // Try to keep JSON responses as JSON
    const ct = r.headers.get("content-type") || "";
    if (ct.includes("application/json")) {
      res.setHeader("content-type", "application/json");
      return res.send(text);
    }

    res.setHeader("content-type", ct || "text/plain");
    return res.send(text);
  } catch (e) {
    return res.status(502).json({ error: `NodeOS proxy error: ${String(e)}` });
  }
}
