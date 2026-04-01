export default async function handler(req, res) {
  try {
    // Server-side (inside docker network) can reach the api service by name
    const upstream = await fetch("http://api:8000/health");

    const text = await upstream.text();
    res.status(upstream.status);
    res.setHeader("Content-Type", upstream.headers.get("content-type") || "application/json");
    return res.send(text);
  } catch (err) {
    return res.status(502).json({ status: "error", error: String(err) });
  }
}
