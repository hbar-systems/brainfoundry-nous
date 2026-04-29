// ui/pages/api/bf/[...path].js
// Raw-passthrough proxy: Next.js default bodyParser breaks multipart uploads
// by consuming the stream and leaving req.body undefined. We disable the
// built-in parser and forward the raw body for any method that has one.

export const config = {
  api: {
    bodyParser: false,
    responseLimit: false,
  },
};

async function readBody(req) {
  const chunks = [];
  for await (const chunk of req) {
    chunks.push(typeof chunk === "string" ? Buffer.from(chunk) : chunk);
  }
  return Buffer.concat(chunks);
}

export default async function handler(req, res) {
  const base = process.env.API_INTERNAL_URL || "http://api:8000";
  const pathParts = req.query.path || [];
  const path = Array.isArray(pathParts) ? pathParts.join("/") : String(pathParts);
  const qs = req.url.includes("?") ? req.url.slice(req.url.indexOf("?")) : "";
  const url = `${base.replace(/\/$/, "")}/${path}${qs}`;

  try {
    const headers = {};
    if (req.headers["content-type"]) headers["content-type"] = req.headers["content-type"];
    if (req.headers["content-length"]) headers["content-length"] = req.headers["content-length"];
    const apiKey = process.env.BRAIN_API_KEY || req.headers["x-api-key"] || "";
    if (apiKey) headers["x-api-key"] = apiKey;
    if (req.headers["authorization"]) headers["authorization"] = req.headers["authorization"];

    let body;
    if (req.method !== "GET" && req.method !== "HEAD") {
      body = await readBody(req);
    }

    const r = await fetch(url, { method: req.method, headers, body });
    res.status(r.status);

    const ct = r.headers.get("content-type") || "";

    // Server-Sent Events (streaming chat): passthrough the chunks as they arrive.
    // Buffering would defeat the whole point of streaming.
    if (ct.includes("text/event-stream")) {
      res.setHeader("content-type", "text/event-stream");
      res.setHeader("cache-control", "no-cache, no-transform");
      res.setHeader("x-accel-buffering", "no"); // disable buffering on proxies (Caddy/Nginx)
      const reader = r.body.getReader();
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        res.write(value);
        // Flush each chunk immediately if the response object supports it.
        if (typeof res.flush === "function") res.flush();
      }
      return res.end();
    }

    // Default: buffer + send (preserves prior behavior for JSON / text endpoints).
    const text = await r.text();
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
