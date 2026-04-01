// ui/lib/brain.js
const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000";

export async function fetchTags(signal) {
  const r = await fetch(`${API_BASE}/brain/tags`, { signal, cache: "no-store" });
  if (!r.ok) throw new Error(`/brain/tags ${r.status}`);
  // Accept either [{name,count}] or {tags:[...]}
  const data = await r.json();
  return Array.isArray(data) ? data : (data.tags || []);
}

export async function fetchDocsByTags(tags, signal) {
  const qs = new URLSearchParams({ tags: tags.join(",") }).toString();
  const r = await fetch(`${API_BASE}/brain/docs?${qs}`, { signal, cache: "no-store" });
  if (!r.ok) throw new Error(`/brain/docs ${r.status}`);
  const data = await r.json();
  // Accept ["a.txt"], {documents:[...]}, or [{document:"a.txt"}]
  if (Array.isArray(data)) return data.map(d => (typeof d === "string" ? d : (d.document || "")));
  if (Array.isArray(data.documents)) return data.documents;
  return [];
}

export async function freeTextSearch(query, limit = 10, signal) {
  const r = await fetch(`${API_BASE}/documents/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, limit }),
    signal,
    cache: "no-store",
  });
  if (!r.ok) throw new Error(`/documents/search ${r.status}`);
  const data = await r.json();
  // Accept array or {results:[...]}
  return Array.isArray(data) ? data : (data.results || []);
}

export async function uploadFiles(files) {
  const form = new FormData();
  files.forEach(f => form.append("files", f, f.name));
  const r = await fetch(`${API_BASE}/documents/upload`, { method: "POST", body: form });
  if (!r.ok) throw new Error(`/documents/upload ${r.status}`);
  return r.json().catch(() => ({}));
}
