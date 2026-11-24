// Knowledge page card "Bring files from your computer" (2026-11-03, docs/IMPORT.md "From your laptop").
// Mints the one-time import token, shows the one command to paste on a Mac or on Windows, and lists
// what arrived while the helper runs: documents wait under Pending for approval, music is kept as
// files in the member's in/<date>/import/. The token is shown once and lives only in this page.
import { useState, useEffect, useRef } from "react";
import { importWords } from "./importText";
import { arrivedCounts } from "./moveInPlan";

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

export default function LaptopImportCard({ btn, onArrived, lang = "en" }) {
  const T = importWords(lang);
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
      const n = arrivedCounts(j.run).docs;
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
        setMint({ error: (j.error && j.error.message) || j.detail || T.lapCouldNot(r.status) });
        return;
      }
      seen.current = 0;
      setMint({ token: j.token, expires_at: j.expires_at });
      loadStatus();
    } catch (err) {
      setMint({ error: T.lapCouldNot(err.message) });
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
  // IMPORT-PACE-1: the exact counts of the run (the list above keeps only the newest 500)
  const nDocs = arrivedCounts(run).docs;
  const nMusic = arrivedCounts(run).audio;
  const tab = (key, label) => (
    <button type="button" onClick={() => { setOs(key); setCopied(false); }}
      style={{ background: "none", border: "none", padding: "4px 10px 4px 0", cursor: "pointer", fontSize: 13,
        color: os === key ? ACCENT : MUTED, textDecoration: os === key ? "underline" : "none" }}>{label}</button>
  );

  return (
    <section style={{ padding: 18, border: `1px solid ${BORDER}`, background: SURFACE, borderRadius: 12, marginBottom: 24 }}>
      <div style={{ fontSize: 15, color: TEXT, marginBottom: 6 }}>{T.lapTitle}</div>
      <div style={{ fontSize: 13, color: MUTED, lineHeight: 1.7 }}>
        <div>{T.lapSub1}</div>
        <div>{T.lapSub2}</div>
      </div>

      {!(mint && mint.token) && (
        <button type="button" onClick={start} disabled={mint && mint.busy}
          style={{ ...btn, marginTop: 12, opacity: mint && mint.busy ? 0.5 : 1 }}>
          {mint && mint.busy ? T.lapStarting : T.lapStart}
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
              ? T.lapMacHow
              : T.lapWinHow}
          </div>
          <pre style={{ whiteSpace: "pre-wrap", wordBreak: "break-all", fontSize: 12, color: TEXT, background: "#0e0c0b",
            border: `1px solid ${BORDER}`, borderRadius: 8, padding: 10, margin: "6px 0 0 0" }}>{cmd}</pre>
          <div style={{ display: "flex", gap: 12, alignItems: "center", marginTop: 8 }}>
            <button type="button" onClick={copy} style={btn}>{copied ? T.lapCopied : T.lapCopy}</button>
            <button type="button" onClick={start} style={{ ...btn, background: "none", color: MUTED }}>{T.lapNew}</button>
          </div>
          <div style={{ fontSize: 12, color: MUTED, lineHeight: 1.7, marginTop: 8 }}>
            {os === "mac"
              ? T.lapMacTip
              : T.lapWinTip}
            {" "}{T.lapOnce(fmtTime(mint.expires_at))}
          </div>
        </div>
      )}

      {arrived.length > 0 && (
        <div style={{ fontSize: 13, color: TEXT, marginTop: 14, lineHeight: 1.6 }}>
          <div style={{ color: run && run.open ? ACCENT : MUTED }}>
            {run && run.open ? T.lapNow : T.lapLast}: {T.lapDocs(nDocs)}
            {nMusic ? T.lapMusic(nMusic) : ""}.
          </div>
          {docs.length > 0 && (
            <div style={{ marginTop: 6 }}>
              <div style={{ color: MUTED }}>{T.lapWaiting}</div>
              {docs.slice(-12).reverse().map((a) => <div key={a.proposal_id || a.path}>{a.path}</div>)}
              {nDocs > 12 && <div style={{ color: MUTED }}>{T.lapMore(nDocs - 12)}</div>}
            </div>
          )}
          {music.length > 0 && (
            <div style={{ marginTop: 6 }}>
              <div style={{ color: MUTED }}>
                {audioTo === "in"
                  ? T.lapKeptIn
                  : T.lapKept}
              </div>
              {music.slice(-12).reverse().map((a) => <div key={a.where || a.path} style={{ color: APPROVE }}>{a.where || a.path}</div>)}
              {nMusic > 12 && <div style={{ color: MUTED }}>{T.lapMore(nMusic - 12)}</div>}
            </div>
          )}
        </div>
      )}
    </section>
  );
}
