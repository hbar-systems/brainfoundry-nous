import { useMemo, useState } from "react";

async function postCommand(body) {
  const r = await fetch(`/api/bf/v1/brain/command`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await r.json().catch(() => ({}));
  return { ok: r.ok, status: r.status, data };
}

export default function KernelConsole() {
  const [clientId, setClientId] = useState("demo");
  const [command, setCommand] = useState("echo");
  const [payloadText, setPayloadText] = useState("hello");
  const [token, setToken] = useState("");
  const [last, setLast] = useState(null);
  const [busy, setBusy] = useState(false);

  const payload = useMemo(() => {
    const c = command.trim().toLowerCase();
    if (c.startsWith("echo")) return { text: payloadText };
    if (c.startsWith("memory append")) return { text: payloadText };
    return {};
  }, [command, payloadText]);

  const doPropose = async () => {
    setBusy(true);
    try {
      const res = await postCommand({ command, client_id: clientId, payload });
      setLast(res);
      const t = res?.data?.data?.token;
      if (t) setToken(t);
    } finally {
      setBusy(false);
    }
  };

  const doConfirm = async () => {
    setBusy(true);
    try {
      const res = await postCommand({ command, client_id: clientId, payload, confirm_token: token || undefined });
      setLast(res);
    } finally {
      setBusy(false);
    }
  };

  const doConfirmBadToken = async () => {
    setBusy(true);
    try {
      const res = await postCommand({ command, client_id: clientId, payload, confirm_token: "CONFIRM-DOESNOTEXIST" });
      setLast(res);
    } finally {
      setBusy(false);
    }
  };

  const inputStyle = {
    width: "100%",
    padding: "10px",
    borderRadius: "8px",
    border: "1px solid #1e1e1e",
    backgroundColor: "#1a1a1a",
    color: "#e5e5e5",
    fontSize: "14px",
    outline: "none",
    boxSizing: "border-box",
  };

  const btnStyle = {
    padding: "10px 14px",
    borderRadius: "8px",
    border: "1px solid #333",
    backgroundColor: "#1a1a1a",
    color: "#e5e5e5",
    cursor: "pointer",
    fontSize: "13px",
  };

  return (
    <div style={{ padding: "40px 32px", maxWidth: "1100px", margin: "0 auto" }}>
      <div style={{ marginBottom: "32px" }}>
        <h1 style={{ fontSize: "26px", fontWeight: "700", margin: "0 0 6px 0", color: "#e5e5e5" }}>Kernel</h1>
        <p style={{ color: "#444", fontSize: "13px", margin: 0 }}>
          Governance boundary — PROPOSE → CONFIRM, permit-gated mutation.
        </p>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "16px" }}>
        <div style={{ backgroundColor: "#111", border: "1px solid #1e1e1e", borderRadius: "12px", padding: "24px" }}>
          <div style={{ display: "grid", gap: "12px" }}>
            <label>
              <div style={{ fontSize: "12px", color: "#555", marginBottom: "6px", textTransform: "uppercase", letterSpacing: "0.06em" }}>client_id</div>
              <input value={clientId} onChange={e => setClientId(e.target.value)} style={inputStyle} />
            </label>
            <label>
              <div style={{ fontSize: "12px", color: "#555", marginBottom: "6px", textTransform: "uppercase", letterSpacing: "0.06em" }}>command</div>
              <input value={command} onChange={e => setCommand(e.target.value)} placeholder='echo, audit tail 10, memory append...' style={inputStyle} />
            </label>
            <label>
              <div style={{ fontSize: "12px", color: "#555", marginBottom: "6px", textTransform: "uppercase", letterSpacing: "0.06em" }}>payload.text</div>
              <input value={payloadText} onChange={e => setPayloadText(e.target.value)} style={inputStyle} />
            </label>
            <label>
              <div style={{ fontSize: "12px", color: "#555", marginBottom: "6px", textTransform: "uppercase", letterSpacing: "0.06em" }}>confirm_token</div>
              <input value={token} onChange={e => setToken(e.target.value)} placeholder="(auto-filled after PROPOSE)" style={inputStyle} />
            </label>
            <div style={{ display: "flex", gap: "10px", flexWrap: "wrap", marginTop: "4px" }}>
              <button onClick={doPropose} disabled={busy} style={btnStyle}>PROPOSE</button>
              <button onClick={doConfirm} disabled={busy || !token} style={{ ...btnStyle, opacity: !token ? 0.4 : 1 }}>CONFIRM</button>
              <button onClick={doConfirmBadToken} disabled={busy} style={btnStyle}>CONFIRM (bad token)</button>
            </div>
            <div style={{ fontSize: "12px", color: "#333", marginTop: "4px" }}>
              Try <code style={{ color: "#555" }}>__does_not_exist__</code> to see KERNEL_UNKNOWN_COMMAND.
            </div>
          </div>
        </div>

        <div style={{ backgroundColor: "#111", border: "1px solid #1e1e1e", borderRadius: "12px", padding: "24px" }}>
          <div style={{ fontSize: "12px", color: "#555", marginBottom: "12px", textTransform: "uppercase", letterSpacing: "0.06em" }}>last response</div>
          <pre style={{ margin: 0, whiteSpace: "pre-wrap", wordBreak: "break-word", fontSize: "12px", lineHeight: "1.5", color: last ? "#aaa" : "#333", fontFamily: "monospace" }}>
            {last ? JSON.stringify(last, null, 2) : "No requests yet."}
          </pre>
        </div>
      </div>

      <div style={{ marginTop: "16px", fontSize: "12px", color: "#333" }}>
        Endpoint: <code style={{ color: "#444" }}>/api/bf/v1/brain/command</code>
      </div>
    </div>
  );
}
