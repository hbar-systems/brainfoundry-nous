// ui/pages/api/bf/[...path].js
// Raw-passthrough proxy: Next.js default bodyParser breaks multipart uploads
// by consuming the stream and leaving req.body undefined. We disable the
// built-in parser and forward the raw body for any method that has one.
//
// The app lane (2026-10-16, ui/lib/appLane.js): this proxy holds the owner key, so it refuses any
// request from a page that is not the console itself (an app frame has Origin "null" and
// Sec-Fetch-Site cross-site). An app's own files and backend pass, without the owner key; app
// files carry the sandbox CSP and, for HTML, the storage shim.

import { decide, corsHeaders, injectShim, APP_CSP } from "../../../lib/appLane";

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

  const lane = decide(pathParts, req.method, req.headers);
  if (lane.action === "refuse") {
    return res.status(lane.status).json({ error: lane.error });
  }
  if (lane.cors) {
    for (const [k, v] of Object.entries(corsHeaders(req.headers))) res.setHeader(k, v);
    if (req.method === "OPTIONS") return res.status(204).end();
  }
  if (lane.appFile) res.setHeader("content-security-policy", APP_CSP);

  try {
    const headers = {};
    if (req.headers["content-type"]) headers["content-type"] = req.headers["content-type"];
    if (req.headers["content-length"]) headers["content-length"] = req.headers["content-length"];
    // The owner key goes only on requests from the console's own pages (lane.ownerKey). App files
    // and app-frame calls to an app backend go without it, and without the caller's credentials.
    if (lane.ownerKey) {
      const apiKey = process.env.BRAIN_API_KEY || req.headers["x-api-key"] || "";
      if (apiKey) headers["x-api-key"] = apiKey;
      if (req.headers["authorization"]) headers["authorization"] = req.headers["authorization"];
    }

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

    // Default: buffer the body as raw bytes and pass through. Using r.text()
    // here UTF-8-decodes binary responses (PNG, GLB, fonts, etc.), corrupting
    // them in transit. Buffer-based passthrough is binary-safe for everything
    // — text bodies (JSON, JS, CSS, HTML) survive because their bytes ARE
    // valid UTF-8, and the upstream content-type header decides how the
    // browser parses them. First hit was brain-app PNGs rendering as white
    // squares; GLBs failed to parse and silently dropped to procedural
    // fallback.
    let buf = Buffer.from(await r.arrayBuffer());
    if (lane.appFile && r.ok && ct.includes("text/html")) {
      buf = Buffer.from(injectShim(buf.toString("utf8")), "utf8");
    }
    res.setHeader("content-type", ct || "application/octet-stream");
    return res.send(buf);
  } catch (e) {
    return res.status(502).json({ error: String(e) });
  }
}
