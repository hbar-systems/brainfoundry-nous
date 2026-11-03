// Knowledge page card "Bring files from your computer" (2026-11-03, docs/IMPORT.md "From your laptop").
// Mints the one-time import token, shows the one command to paste on a Mac or on Windows, and lists
// what arrived while the helper runs: documents wait under Pending for approval, music is kept as
// files in the member's in/<date>/import/. The token is shown once and lives only in this page.
import { useState, useEffect, useRef } from "react";

const API_BASE = "/api/bf";
const SURFACE = "#161310";
const BORDER = "#2a2420";
const TEXT = "#e8e0d5";
const MUTED = "#6b5f52";
const ACCENT = "#c9a96e";
const APPROVE = "#7a9e6e";
const REJECT = "#a96e6e";

export function laptopCommands(base, token) {
  const helper = `${base}/documents/import-laptop/helper.py`;
  return {
    mac: `curl -fsSLo brain_import.py "${helper}" && python3 brain_import.py --brain "${base}" --token ${token}`,
    windows: `curl.exe -fsSLo brain_import.py "${helper}"; python brain_import.py --brain "${base}" --token ${token}`,
  };
}

const fmtTime = (s) => new Date(s * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

export default function LaptopImportCard({ btn, onArrived }) {
  const [mint, setMint] = useState(null); // null | {busy} | {token, expires_at} | {error}
  const [os, setOs] = useState("mac");
  const [copied, setCopied] = useState(false);
  const [run, setRun] = useState(null);
  const [audioTo, setAudioTo] = useState("in");
  const seen = useRef(0);
  const base = typeof window === "undefined" ? "" : `${window.location.origin}${API_BASE}`;

  useEffect(() => {
    if (typeof navigator !== "undefined" && /Windows/i.test(navigator.userAgent || "")) setOs("windows");
  }, []);

  const loadStatus = async () => {
    try {
      const r = await fetch(`${API_BASE}/documents/import-laptop/status`, { cache: "no-store" });
      if (!r.ok) return;
      const j = await r.json();
      setAudioTo(j.audio_to || "in");
      setRun(j.run || null);
      const n = (j.run && j.run.arrived) ? j.run.arrived.filter((a) => a.kind === "knowledge").length : 0;
      if (n > seen.current && onArrived) onArrived();
      seen.current = n;
    } catch (e) {
      // Quiet: the card keeps its last list if the brain is not answering.
    }
  };

  // Poll while a token is open (and once on load, so a run started earlier still shows).
  useEffect(() => { loadStatus(); }, []);
  // This token's run is the one whose expiry matches; once it closes (the helper finished), polling stops.
  const open = mint && mint.token && Date.now() / 1000 < mint.expires_at && !(run && !run.open && run.expires_at === mint.expires_at);
  useEffect(() => {
    if (!open) return undefined;
    const t = setInterval(loadStatus, 4000);
    return () => clearInterval(t);
  }, [open]);

  const start = async () => {
    setMint({ busy: true });
    setCopied(false);
    try {
      const r = await fetch(`${API_BASE}/documents/import-laptop/token`, { method: "POST" });
      const j = await r.json().catch(() => ({}));
      if (!r.ok) {
        setMint({ error: (j.error && j.error.message) || j.detail || `Could not start (${r.status}).` });
        return;
      }
      seen.current = 0;
      setMint({ token: j.token, expires_at: j.expires_at });
      loadStatus();
    } catch (err) {
      setMint({ error: `Could not start: ${err.message}` });
    }
  };

  const cmd = mint && mint.token ? laptopCommands(base, mint.token)[os] : "";
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(cmd);
      setCopied(true);
    } catch (e) {
      setCopied(false);
    }
  };

  const arrived = (run && run.arrived) || [];
  const docs = arrived.filter((a) => a.kind === "knowledge");
  const music = arrived.filter((a) => a.kind === "audio");
  const tab = (key, label) => (
    <button type="button" onClick={() => { setOs(key); setCopied(false); }}
      style={{ background: "none", border: "none", padding: "4px 10px 4px 0", cursor: "pointer", fontSize: 13,
        color: os === key ? ACCENT : MUTED, textDecoration: os === key ? "underline" : "none" }}>{label}</button>
  );

  return (
    <section style={{ padding: 18, border: `1px solid ${BORDER}`, background: SURFACE, borderRadius: 12, marginBottom: 24 }}>
      <div style={{ fontSize: 15, color: TEXT, marginBottom: 6 }}>Bring files from your computer</div>
      <div style={{ fontSize: 13, color: MUTED, lineHeight: 1.7 }}>
        <div>A small program runs on your computer and asks you, folder by folder, what to bring.</div>
        <div>It never sends passwords, keys or hidden files. Documents wait below for your yes; music is kept as files for your music tools.</div>
      </div>

      {!(mint && mint.token) && (
        <button type="button" onClick={start} disabled={mint && mint.busy}
          style={{ ...btn, marginTop: 12, opacity: mint && mint.busy ? 0.5 : 1 }}>
          {mint && mint.busy ? "Starting..." : "Start"}
        </button>
      )}
      {mint && mint.error && (
        <div style={{ fontSize: 13, color: REJECT, marginTop: 10, lineHeight: 1.6 }}>{mint.error}</div>
      )}

      {mint && mint.token && (
        <div style={{ marginTop: 12 }}>
          <div>{tab("mac", "Mac")}{tab("windows", "Windows")}</div>
          <div style={{ fontSize: 13, color: MUTED, lineHeight: 1.7, marginTop: 4 }}>
            {os === "mac"
              ? "Open Terminal (Applications, Utilities, Terminal), paste this line, press Return:"
              : "Open PowerShell (Start menu, type PowerShell), paste this line, press Enter:"}
          </div>
          <pre style={{ whiteSpace: "pre-wrap", wordBreak: "break-all", fontSize: 12, color: TEXT, background: "#0e0c0b",
            border: `1px solid ${BORDER}`, borderRadius: 8, padding: 10, margin: "6px 0 0 0" }}>{cmd}</pre>
          <div style={{ display: "flex", gap: 12, alignItems: "center", marginTop: 8 }}>
            <button type="button" onClick={copy} style={btn}>{copied ? "Copied" : "Copy"}</button>
            <button type="button" onClick={start} style={{ ...btn, background: "none", color: MUTED }}>New line</button>
          </div>
          <div style={{ fontSize: 12, color: MUTED, lineHeight: 1.7, marginTop: 8 }}>
            {os === "mac"
              ? "If your Mac offers to install developer tools, say yes, then paste the line again."
              : "If Windows opens the Microsoft Store for Python, install it, then paste the line again."}
            {" "}This line works once, until {fmtTime(mint.expires_at)}. Keep it to yourself.
          </div>
        </div>
      )}

      {arrived.length > 0 && (
        <div style={{ fontSize: 13, color: TEXT, marginTop: 14, lineHeight: 1.6 }}>
          <div style={{ color: run && run.open ? ACCENT : MUTED }}>
            {run && run.open ? "Arriving now" : "Last time"}: {docs.length} document{docs.length === 1 ? "" : "s"}
            {music.length ? `, ${music.length} music file${music.length === 1 ? "" : "s"}` : ""}.
          </div>
          {docs.length > 0 && (
            <div style={{ marginTop: 6 }}>
              <div style={{ color: MUTED }}>Waiting for your yes under Pending memory proposals below:</div>
              {docs.slice(-12).reverse().map((a) => <div key={a.proposal_id || a.path}>{a.path}</div>)}
              {docs.length > 12 && <div style={{ color: MUTED }}>and {docs.length - 12} more</div>}
            </div>
          )}
          {music.length > 0 && (
            <div style={{ marginTop: 6 }}>
              <div style={{ color: MUTED }}>
                {audioTo === "in"
                  ? "Kept for your music tools (in your in folder, listed in audio.tsv):"
                  : "Kept on your brain for your music tools:"}
              </div>
              {music.slice(-12).reverse().map((a) => <div key={a.where || a.path} style={{ color: APPROVE }}>{a.where || a.path}</div>)}
              {music.length > 12 && <div style={{ color: MUTED }}>and {music.length - 12} more</div>}
            </div>
          )}
        </div>
      )}
    </section>
  );
}
