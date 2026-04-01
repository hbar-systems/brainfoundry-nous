const API_BASE = "/api/bf";

export async function fetchTags(signal) {
  const r = await fetch(`${API_BASE}/brain/tags`, { signal, cache: "no-store" });
  if (!r.ok) throw new Error(`/brain/tags ${r.status}`);
  const data = await r.json();
  return Array.isArray(data) ? data : (data.tags || []);
}

export async function fetchDocsByTags(tags, signal) {
  const qs = new URLSearchParams({ tags: tags.join(",") }).toString();
  const r = await fetch(`${API_BASE}/brain/docs?${qs}`, { signal, cache: "no-store" });
  if (!r.ok) throw new Error(`/brain/docs ${r.status}`);
  const data = await r.json();
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
  return Array.isArray(data) ? data : (data.results || []);
}

export async function uploadFiles(files) {
  const form = new FormData();
  files.forEach(f => form.append("files", f, f.name));
  const r = await fetch(`${API_BASE}/documents/upload`, { method: "POST", body: form });
  if (!r.ok) throw new Error(`/documents/upload ${r.status}`);
  return r.json().catch(() => ({}));
}
