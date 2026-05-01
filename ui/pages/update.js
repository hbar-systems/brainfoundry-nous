import Head from 'next/head'
import { useEffect, useRef, useState } from 'react'

// Phases the page can be in. The state machine maps to what the user sees:
//   idle      → show version banner + "Pull latest" button
//   running   → SSE open, log streaming
//   rebuilding→ stream dropped after we saw the rebuild marker; poll version
//   verifying → version-info call in flight after a rebuild
//   success   → new commit confirmed; show green banner
//   error     → preflight or run-time error; show red banner + raw error

const COLORS = {
  bg: '#0e0c0b',
  surface: '#1c1814',
  surface2: '#161310',
  text: '#e8e0d5',
  muted: '#8b7d6e',
  mutedDim: '#6b5f52',
  accent: '#c9a96e',
  border: '#2a2420',
  success: { bg: '#1e3a26', text: '#7fc99c' },
  warn: { bg: '#3a3520', text: '#d4b86a' },
  err: { bg: '#3a2020', text: '#d49a9a' },
}

function shortSha(sha) {
  if (!sha || typeof sha !== 'string') return '—'
  if (sha === 'unknown') return 'unknown'
  return sha.slice(0, 7)
}

export default function Update() {
  const [phase, setPhase] = useState('idle')
  const [version, setVersion] = useState(null)
  const [versionLoading, setVersionLoading] = useState(true)
  const [logs, setLogs] = useState([]) // [{kind:'log'|'meta'|'error'|'done', text}]
  const [errorMsg, setErrorMsg] = useState(null)
  const [postUpdateCommit, setPostUpdateCommit] = useState(null)
  const startCommitRef = useRef(null) // commit at click time, for "did it change?"
  const logBoxRef = useRef(null)
  const abortRef = useRef(null)

  // Version banner — call /admin/version-info on mount and after success.
  const refreshVersion = async () => {
    setVersionLoading(true)
    try {
      const r = await fetch('/api/bf/admin/version-info')
      if (r.ok) {
        const data = await r.json()
        setVersion(data)
        return data
      }
    } catch {
      // Silent — banner just shows "—" until next refresh.
    } finally {
      setVersionLoading(false)
    }
    return null
  }

  useEffect(() => { refreshVersion() }, [])

  // Auto-scroll log box on each append.
  useEffect(() => {
    if (logBoxRef.current) {
      logBoxRef.current.scrollTop = logBoxRef.current.scrollHeight
    }
  }, [logs])

  const appendLog = (entry) => setLogs((prev) => [...prev, entry])

  const startUpdate = async () => {
    if (phase === 'running' || phase === 'rebuilding' || phase === 'verifying') return
    setLogs([])
    setErrorMsg(null)
    setPostUpdateCommit(null)
    setPhase('running')
    startCommitRef.current = version?.current || null

    const ctrl = new AbortController()
    abortRef.current = ctrl

    let r
    try {
      r = await fetch('/api/bf/admin/update', {
        method: 'POST',
        signal: ctrl.signal,
        headers: { 'Accept': 'text/event-stream' },
      })
    } catch (e) {
      // Network failure before stream opens — distinct from a rebuild drop.
      setErrorMsg(`Could not reach the brain: ${e.message}`)
      setPhase('error')
      return
    }

    if (!r.ok) {
      let detail = `HTTP ${r.status}`
      try {
        const data = await r.json()
        if (data?.detail) detail = data.detail
      } catch {}
      setErrorMsg(detail)
      setPhase('error')
      return
    }

    // Stream the SSE response. Mirrors the reader pattern in chat.js so we
    // don't fork a second SSE consumer convention.
    let sawRebuildMarker = false
    let sawDone = false
    try {
      const reader = r.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { value, done } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const frames = buffer.split('\n\n')
        buffer = frames.pop()

        for (const frame of frames) {
          if (!frame.startsWith('data: ')) continue
          const payload = frame.slice(6).trim()
          if (payload === '[DONE]') { sawDone = true; continue }
          let parsed
          try { parsed = JSON.parse(payload) } catch { continue }

          if (parsed.type === 'log') {
            appendLog({ kind: 'log', text: parsed.line })
            // The shell script prints "==> Rebuilding services" right before
            // it kicks off `docker compose up -d --build`. From this point on,
            // any connection drop is *expected* — the api container is about
            // to be replaced. Latching this lets us treat the drop as success
            // rather than as a network error.
            if (typeof parsed.line === 'string' && /Rebuilding services/i.test(parsed.line)) {
              sawRebuildMarker = true
            }
          } else if (parsed.type === 'start') {
            appendLog({ kind: 'meta', text: `started in ${parsed.cwd}` })
          } else if (parsed.type === 'done') {
            appendLog({ kind: 'meta', text: `script exited (rc=${parsed.returncode})` })
          } else if (parsed.type === 'error') {
            appendLog({ kind: 'error', text: parsed.message })
          }
        }
      }
    } catch (e) {
      // Stream broke. If we already saw the rebuild marker, this is the
      // expected mid-rebuild disconnect. Otherwise, a real error.
      if (!sawRebuildMarker) {
        setErrorMsg(`Stream interrupted before rebuild started: ${e.message}`)
        setPhase('error')
        return
      }
    }

    if (sawRebuildMarker) {
      // Container is restarting; the version-info poll will tell us when it's back.
      setPhase('rebuilding')
      pollUntilUpdated()
    } else if (sawDone) {
      // Stream completed cleanly without a rebuild marker — usually means
      // "already up to date" (the script exits early in that case).
      setPhase('idle')
      refreshVersion()
    } else {
      setErrorMsg('Stream closed unexpectedly without a rebuild signal.')
      setPhase('error')
    }
  }

  // Poll /admin/version-info every few seconds until either the commit
  // changes (success) or we hit the deadline (error). Up to ~3 minutes.
  const pollUntilUpdated = async () => {
    const startCommit = startCommitRef.current
    const deadline = Date.now() + 3 * 60 * 1000
    setPhase('verifying')

    // Brief grace period so we don't immediately hammer a still-down container.
    await new Promise((res) => setTimeout(res, 6000))

    while (Date.now() < deadline) {
      try {
        const r = await fetch('/api/bf/admin/version-info')
        if (r.ok) {
          const data = await r.json()
          if (data?.current && data.current !== 'unknown' && data.current !== startCommit) {
            setVersion(data)
            setPostUpdateCommit(data.current)
            setPhase('success')
            return
          }
        }
      } catch {
        // 502 / network error during restart — keep polling.
      }
      await new Promise((res) => setTimeout(res, 4000))
    }

    setErrorMsg('Brain did not come back online within 3 minutes. Check `docker compose logs api` on the host.')
    setPhase('error')
  }

  const manualRetryVerify = () => {
    if (phase !== 'rebuilding' && phase !== 'error') return
    pollUntilUpdated()
  }

  // ── Layout ─────────────────────────────────────────────────────────────

  const preflightErr = version?.preflight_error
  const upToDate = version && version.behind_by === 0
  const buttonDisabled =
    !!preflightErr ||
    phase === 'running' ||
    phase === 'rebuilding' ||
    phase === 'verifying'

  return (
    <>
      <Head><title>Update · BrainFoundry</title></Head>
      <div style={{ padding: '40px 32px', maxWidth: '900px', margin: '0 auto', fontFamily: 'Lora, ui-serif, serif' }}>

        <div style={{ marginBottom: '28px' }}>
          <p style={{
            color: COLORS.accent,
            fontSize: '11px',
            letterSpacing: '0.15em',
            textTransform: 'uppercase',
            fontFamily: 'DM Mono, monospace',
            margin: '0 0 6px 0',
          }}>
            brainfoundry-nous · self-update
          </p>
          <h1 style={{ fontSize: '32px', color: COLORS.text, margin: '0 0 6px 0', fontWeight: 600 }}>
            Update your brain
          </h1>
          <p style={{ color: COLORS.muted, fontSize: '14px', margin: 0, lineHeight: '1.55' }}>
            Pulls the latest brain template from{' '}
            <a href="https://github.com/hbar-systems/brainfoundry-nous" target="_blank" rel="noreferrer" style={{ color: COLORS.accent }}>
              github.com/hbar-systems/brainfoundry-nous
            </a>{' '}
            and rebuilds in place. Your chats, documents, and models persist —
            only the code is replaced.
          </p>
        </div>

        {/* Version banner */}
        <div style={{
          padding: '16px 20px',
          backgroundColor: COLORS.surface,
          border: `1px solid ${COLORS.border}`,
          borderRadius: '10px',
          marginBottom: '20px',
          display: 'flex',
          flexWrap: 'wrap',
          gap: '24px',
          fontFamily: 'DM Mono, ui-monospace, monospace',
          fontSize: '12px',
        }}>
          <div>
            <div style={{ color: COLORS.mutedDim, fontSize: '10px', letterSpacing: '0.1em', textTransform: 'uppercase', marginBottom: '4px' }}>currently running</div>
            <div style={{ color: COLORS.text, fontSize: '14px' }}>
              {versionLoading ? '…' : shortSha(version?.current)}
              {version?.brain_version ? <span style={{ color: COLORS.muted, marginLeft: '8px' }}>v{version.brain_version}</span> : null}
            </div>
          </div>
          <div>
            <div style={{ color: COLORS.mutedDim, fontSize: '10px', letterSpacing: '0.1em', textTransform: 'uppercase', marginBottom: '4px' }}>latest on origin/main</div>
            <div style={{ color: COLORS.text, fontSize: '14px' }}>
              {versionLoading ? '…' : shortSha(version?.latest)}
            </div>
          </div>
          <div>
            <div style={{ color: COLORS.mutedDim, fontSize: '10px', letterSpacing: '0.1em', textTransform: 'uppercase', marginBottom: '4px' }}>commits behind</div>
            <div style={{
              color: version?.behind_by > 0 ? COLORS.warn.text : COLORS.muted,
              fontSize: '14px',
            }}>
              {versionLoading ? '…' : (version?.behind_by ?? '—')}
            </div>
          </div>
        </div>

        {/* Preflight warning */}
        {preflightErr && (
          <div style={{
            padding: '14px 18px',
            backgroundColor: COLORS.warn.bg,
            color: COLORS.warn.text,
            border: `1px solid ${COLORS.warn.text}40`,
            borderRadius: '8px',
            fontSize: '13px',
            marginBottom: '20px',
            lineHeight: '1.6',
            fontFamily: 'system-ui, sans-serif',
          }}>
            <strong>Update tab not fully wired up on this brain.</strong>
            <div style={{ marginTop: '6px', fontFamily: 'DM Mono, monospace', fontSize: '12px' }}>{preflightErr}</div>
          </div>
        )}

        {/* Action button */}
        <div style={{ marginBottom: '24px' }}>
          <button
            onClick={startUpdate}
            disabled={buttonDisabled}
            style={{
              padding: '12px 22px',
              fontSize: '14px',
              fontFamily: 'system-ui, sans-serif',
              fontWeight: 500,
              color: buttonDisabled ? COLORS.mutedDim : '#0e0c0b',
              backgroundColor: buttonDisabled ? COLORS.surface : COLORS.accent,
              border: `1px solid ${buttonDisabled ? COLORS.border : COLORS.accent}`,
              borderRadius: '8px',
              cursor: buttonDisabled ? 'not-allowed' : 'pointer',
              transition: 'all 0.15s ease',
            }}
          >
            {phase === 'running' ? 'Updating…'
              : phase === 'rebuilding' ? 'Rebuilding…'
              : phase === 'verifying' ? 'Verifying new version…'
              : phase === 'success' ? 'Pull latest from public template'
              : upToDate ? 'Pull latest (already up to date)'
              : 'Pull latest from public template'}
          </button>
          {!upToDate && version?.behind_by > 0 && phase === 'idle' && (
            <span style={{ color: COLORS.muted, fontSize: '13px', marginLeft: '14px', fontFamily: 'system-ui, sans-serif' }}>
              {version.behind_by} new {version.behind_by === 1 ? 'commit' : 'commits'} on origin/main.
            </span>
          )}
        </div>

        {/* Status banners */}
        {phase === 'rebuilding' && (
          <div style={{
            padding: '14px 18px',
            backgroundColor: COLORS.warn.bg,
            color: COLORS.warn.text,
            border: `1px solid ${COLORS.warn.text}40`,
            borderRadius: '8px',
            fontSize: '13px',
            marginBottom: '16px',
            fontFamily: 'system-ui, sans-serif',
          }}>
            Brain is rebuilding. The connection dropped — that&apos;s expected;
            the api container is being replaced. Reload in ~30 seconds, or
            click below to check now.
            <div style={{ marginTop: '8px' }}>
              <button onClick={manualRetryVerify} style={{
                padding: '6px 14px',
                fontSize: '12px',
                color: COLORS.warn.text,
                backgroundColor: 'transparent',
                border: `1px solid ${COLORS.warn.text}`,
                borderRadius: '6px',
                cursor: 'pointer',
                fontFamily: 'DM Mono, monospace',
              }}>Check now</button>
            </div>
          </div>
        )}

        {phase === 'verifying' && (
          <div style={{
            padding: '14px 18px',
            backgroundColor: COLORS.surface,
            color: COLORS.muted,
            border: `1px solid ${COLORS.border}`,
            borderRadius: '8px',
            fontSize: '13px',
            marginBottom: '16px',
            fontFamily: 'system-ui, sans-serif',
          }}>
            Polling /admin/version-info until the new commit shows up…
          </div>
        )}

        {phase === 'success' && (
          <div style={{
            padding: '14px 18px',
            backgroundColor: COLORS.success.bg,
            color: COLORS.success.text,
            border: `1px solid ${COLORS.success.text}40`,
            borderRadius: '8px',
            fontSize: '13px',
            marginBottom: '16px',
            fontFamily: 'system-ui, sans-serif',
          }}>
            Updated to <strong style={{ fontFamily: 'DM Mono, monospace' }}>{shortSha(postUpdateCommit)}</strong>. Brain is healthy.
          </div>
        )}

        {phase === 'error' && errorMsg && (
          <div style={{
            padding: '14px 18px',
            backgroundColor: COLORS.err.bg,
            color: COLORS.err.text,
            border: `1px solid ${COLORS.err.text}40`,
            borderRadius: '8px',
            fontSize: '13px',
            marginBottom: '16px',
            fontFamily: 'DM Mono, monospace',
            whiteSpace: 'pre-wrap',
          }}>
            {errorMsg}
            <div style={{ marginTop: '10px' }}>
              <button onClick={manualRetryVerify} style={{
                padding: '6px 14px',
                fontSize: '12px',
                color: COLORS.err.text,
                backgroundColor: 'transparent',
                border: `1px solid ${COLORS.err.text}`,
                borderRadius: '6px',
                cursor: 'pointer',
              }}>Re-check version</button>
            </div>
          </div>
        )}

        {/* Log viewer */}
        {(logs.length > 0 || phase === 'running' || phase === 'rebuilding') && (
          <div>
            <div style={{ color: COLORS.mutedDim, fontSize: '11px', letterSpacing: '0.12em', textTransform: 'uppercase', fontFamily: 'DM Mono, monospace', marginBottom: '6px' }}>
              update_brain.sh output
            </div>
            <div
              ref={logBoxRef}
              style={{
                backgroundColor: '#08070a',
                border: `1px solid ${COLORS.border}`,
                borderRadius: '8px',
                padding: '14px 16px',
                fontFamily: 'DM Mono, ui-monospace, monospace',
                fontSize: '12px',
                lineHeight: '1.55',
                color: '#cfc6b8',
                height: '420px',
                overflowY: 'auto',
                whiteSpace: 'pre-wrap',
              }}
            >
              {logs.map((entry, i) => (
                <div key={i} style={{
                  color: entry.kind === 'error' ? COLORS.err.text
                       : entry.kind === 'meta' ? COLORS.muted
                       : '#cfc6b8',
                  fontStyle: entry.kind === 'meta' ? 'italic' : 'normal',
                }}>
                  {entry.kind === 'meta' ? `— ${entry.text}` : entry.text}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Footer / fallback path */}
        <div style={{ marginTop: '40px', padding: '18px 20px', backgroundColor: '#161310', border: '1px solid #2a2420', borderRadius: '10px' }}>
          <p style={{ color: '#e8e0d5', fontSize: '13px', margin: '0 0 10px 0', fontWeight: 500, fontFamily: 'system-ui, sans-serif' }}>
            Or update from your laptop terminal (same result)
          </p>
          <p style={{ color: COLORS.mutedDim, fontSize: '12px', margin: '0 0 12px 0', lineHeight: '1.6', fontFamily: 'system-ui, sans-serif' }}>
            If the button above doesn&rsquo;t work or you prefer the command line, you can run the update yourself in four steps:
          </p>
          <ol style={{ color: COLORS.muted, fontSize: '12px', lineHeight: '1.7', paddingLeft: '20px', margin: 0, fontFamily: 'system-ui, sans-serif' }}>
            <li style={{ marginBottom: '8px' }}>
              Open <strong style={{ color: '#e8e0d5' }}>Terminal</strong> (Mac: <code style={{ color: COLORS.muted, fontFamily: 'DM Mono, monospace', fontSize: '11px' }}>Cmd+Space</code> &rarr; type &ldquo;Terminal&rdquo; &rarr; Enter; Linux: usually <code style={{ color: COLORS.muted, fontFamily: 'DM Mono, monospace', fontSize: '11px' }}>Ctrl+Alt+T</code>; Windows: install WSL or use Git Bash).
            </li>
            <li style={{ marginBottom: '8px' }}>
              SSH into your brain (replace <code style={{ color: COLORS.muted, fontFamily: 'DM Mono, monospace', fontSize: '11px' }}>&lt;handle&gt;</code> with your brain&rsquo;s name):
              <pre style={{ background: '#0e0c0b', border: '1px solid #2a2420', borderRadius: '6px', padding: '10px 12px', color: '#e8e0d5', fontSize: '11px', fontFamily: 'DM Mono, monospace', margin: '6px 0 0 0', overflowX: 'auto' }}>
{`ssh -i ~/.ssh/brainfoundry-<handle>.key hbar@<handle>.brainfoundry.ai`}
              </pre>
            </li>
            <li style={{ marginBottom: '8px' }}>
              Move into your brain&rsquo;s directory:
              <pre style={{ background: '#0e0c0b', border: '1px solid #2a2420', borderRadius: '6px', padding: '10px 12px', color: '#e8e0d5', fontSize: '11px', fontFamily: 'DM Mono, monospace', margin: '6px 0 0 0', overflowX: 'auto' }}>
{`cd /home/hbar/brain`}
              </pre>
            </li>
            <li>
              Run the update script:
              <pre style={{ background: '#0e0c0b', border: '1px solid #2a2420', borderRadius: '6px', padding: '10px 12px', color: '#e8e0d5', fontSize: '11px', fontFamily: 'DM Mono, monospace', margin: '6px 0 0 0', overflowX: 'auto' }}>
{`./scripts/update_brain.sh`}
              </pre>
            </li>
          </ol>
          <p style={{ color: COLORS.mutedDim, fontSize: '11px', margin: '14px 0 0 0', lineHeight: '1.6', fontFamily: 'system-ui, sans-serif', fontStyle: 'italic' }}>
            The script does the same thing as the button: backs up your <code style={{ color: COLORS.muted, fontFamily: 'DM Mono, monospace', fontSize: '10px' }}>.env</code>, pulls latest from the public template, rebuilds the brain, and verifies health. Your chats and documents stay intact.
          </p>
        </div>
      </div>
    </>
  )
}
