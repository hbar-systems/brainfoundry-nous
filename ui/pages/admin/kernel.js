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
        <p style={{ color: "#6b5f52", fontSize: "13px", margin: "0 0 18px 0", fontStyle: "italic" }}>
          Governance boundary — PROPOSE → CONFIRM, permit-gated mutation.
        </p>

        <div style={{ background: "#111", border: "1px solid #1e1e1e", borderRadius: 12, padding: 20, color: "#b8ad9e", fontSize: 13, lineHeight: 1.7 }}>
          <div style={{ color: "#c9a96e", fontFamily: "Lora, Georgia, serif", fontSize: 15, marginBottom: 10 }}>What is this page?</div>
          <p style={{ margin: "0 0 10px 0" }}>
            This is the live operator&apos;s window into the <strong style={{ color: "#e5e5e5" }}>authority kernel</strong> — the layer that stands between any command and your brain&apos;s state.
            Nothing writes to memory or runs a mutation here without passing a two-step gate: <strong style={{ color: "#e5e5e5" }}>PROPOSE</strong> (declare intent, get a token) and <strong style={{ color: "#e5e5e5" }}>CONFIRM</strong> (present the token, execute).
          </p>
          <p style={{ margin: "0 0 10px 0" }}>
            You&apos;ll use this page to prove to yourself that sovereignty actually holds — not as a slogan, but as a protocol you can poke at.
          </p>

          <div style={{ color: "#c9a96e", fontFamily: "Lora, Georgia, serif", fontSize: 14, margin: "18px 0 6px 0" }}>Try this</div>
          <ol style={{ margin: 0, paddingLeft: 20 }}>
            <li style={{ marginBottom: 6 }}>
              Leave the defaults (<code style={{ color: "#e5e5e5" }}>client_id: demo</code>, <code style={{ color: "#e5e5e5" }}>command: echo</code>, <code style={{ color: "#e5e5e5" }}>payload.text: hello</code>) and click <strong style={{ color: "#e5e5e5" }}>PROPOSE</strong>. The right panel will show a response with a <code style={{ color: "#e5e5e5" }}>token</code>. That token is auto-filled into the CONFIRM_TOKEN field.
            </li>
            <li style={{ marginBottom: 6 }}>
              Click <strong style={{ color: "#e5e5e5" }}>CONFIRM</strong>. The kernel verifies the token matches the propose, and only then executes the command. You&apos;ll see <code style={{ color: "#e5e5e5" }}>echo</code> return <code style={{ color: "#e5e5e5" }}>hello</code>.
            </li>
            <li style={{ marginBottom: 6 }}>
              Click <strong style={{ color: "#e5e5e5" }}>CONFIRM (bad token)</strong>. This sends a made-up token. The kernel rejects it with <code style={{ color: "#e5e5e5" }}>KERNEL_BAD_CONFIRM_TOKEN</code>. This is what a replay attack looks like from the kernel&apos;s point of view — blocked.
            </li>
            <li>
              Change <strong>command</strong> to <code style={{ color: "#e5e5e5" }}>__does_not_exist__</code> and PROPOSE — the kernel returns <code style={{ color: "#e5e5e5" }}>KERNEL_UNKNOWN_COMMAND</code> before any state is touched. Unknown verbs don&apos;t get partial execution.
            </li>
          </ol>

          <div style={{ color: "#c9a96e", fontFamily: "Lora, Georgia, serif", fontSize: 14, margin: "18px 0 6px 0" }}>What you should see</div>
          <p style={{ margin: 0 }}>
            Every response is a structured JSON envelope: <code style={{ color: "#e5e5e5" }}>{'{ ok, data?, error? }'}</code>. Errors carry a machine-readable code (<code style={{ color: "#e5e5e5" }}>KERNEL_*</code>) — the same codes your own agents, CLIs, and federated peers will see. This is the contract; the UI is just a thin window onto it.
          </p>
        </div>
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
