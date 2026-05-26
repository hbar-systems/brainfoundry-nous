import { useEffect, useRef, useState } from 'react'
import { Panel, PanelGroup, PanelResizeHandle } from 'react-resizable-panels'
import MessageRenderer from '../lib/MessageRenderer'
import CustomSelect from '../lib/CustomSelect'
import { loadModelsAndDefault, persistModelChoice } from '../lib/defaultModel'

const THEME_OPTIONS = [
  { value: 'gold', label: 'gold', swatch: '#c9a96e' },
  { value: 'paper', label: 'paper', swatch: '#8a6e3c' },
  { value: 'sapphire', label: 'sapphire', swatch: '#6b8cce' },
  { value: 'forest', label: 'forest', swatch: '#88a868' },
  { value: 'crimson', label: 'crimson', swatch: '#c87878' },
  { value: 'mono', label: 'mono', swatch: '#b0b0b0' },
]

// Each option's optionStyle previews the font in the dropdown row itself,
// so the operator can see what they're picking before they apply it.
const FONT_OPTIONS = [
  { value: 'system', label: 'System sans', optionStyle: { fontFamily: 'system-ui, -apple-system, sans-serif' } },
  { value: 'inter', label: 'Inter', optionStyle: { fontFamily: '"Inter", system-ui, sans-serif' } },
  { value: 'lora', label: 'Lora', optionStyle: { fontFamily: 'Lora, Georgia, serif' } },
  { value: 'crimson', label: 'Crimson Pro', optionStyle: { fontFamily: '"Crimson Pro", Georgia, serif' } },
  { value: 'dm-mono', label: 'DM Mono', optionStyle: { fontFamily: '"DM Mono", ui-monospace, monospace' } },
  { value: 'jetbrains', label: 'JetBrains Mono', optionStyle: { fontFamily: '"JetBrains Mono", ui-monospace, monospace' } },
]

const FONT_MIGRATION = { ui: 'system', serif: 'lora', mono: 'dm-mono' }

// Reading-pace presets — operator-controlled. One control governs two things
// while the brain is streaming:
//   pxPerFrame — how fast the view scrolls toward the writing edge.
//   cps        — how fast the assistant's text is *revealed* (chars/second).
// The provider streams in bursts; releasing the text at a steady cps turns
// those bursts into a calm, deliberate reading cadence. 'instant' restores
// the old behavior: text appears the moment it arrives, view teleports.
// Acceleration kicks in for both when we fall far behind (giant code dump)
// so a slow pace never strands the operator minutes behind the brain.
const SCROLL_PACE_OPTIONS = [
  { value: 'instant', label: 'instant', pxPerFrame: Infinity, cps: Infinity },
  { value: 'slow', label: 'slow read', pxPerFrame: 1.0, cps: 26 },
  { value: 'normal', label: 'normal', pxPerFrame: 2.2, cps: 70 },
  { value: 'fast', label: 'fast', pxPerFrame: 5, cps: 190 },
]

// The example first conversation — shipped with the template, rendered as the
// chat empty-state while the brain is still the unconfigured persona. This is
// the cold-start fix: it walks a brand-new owner through giving the brain an
// identity before they face an empty Knowledge tab. Canonical long-form copy
// lives in docs/first-conversation.md — keep the two in sync.
function IdentityOnboarding({ onStart }) {
  const lines = [
    "Welcome. I'm your brain — but I don't have a name yet.",
    "Right now I'm running the unedited template persona.",
    'Two things define me before we really start: my name, and your name — the person I belong to and answer to.',
    'Use the button below. It writes both into my persona document, strips the template banner, and reloads me as a named brain.',
    "It's the same step the provisioner runs by hand — you just don't need a terminal for it.",
  ]
  return (
    <div style={{ maxWidth: '640px', width: '100%', margin: '32px auto' }}>
      <div style={{ textAlign: 'center', marginBottom: '22px' }}>
        <div style={{ fontSize: '34px', color: 'var(--accent)', opacity: 0.35 }}>ℏ</div>
        <div style={{ fontFamily: 'var(--font-display)', fontStyle: 'italic', fontSize: '19px', color: 'var(--text)', marginTop: '10px' }}>
          Welcome. Let's give this brain an identity.
        </div>
      </div>

      {/* The brain's scripted first message. */}
      <div style={{ display: 'flex', justifyContent: 'flex-start' }}>
        <div style={{
          maxWidth: '100%',
          padding: '16px 20px',
          borderRadius: '16px',
          background: 'var(--assistant-bg)',
          color: 'var(--assistant-text)',
          border: '1px solid var(--border)',
          fontSize: '14px',
          lineHeight: 1.6,
        }}>
          <div style={{ fontSize: '11px', opacity: 0.6, marginBottom: '8px', fontWeight: 500 }}>Your brain</div>
          {lines.map((l, i) => (
            <div key={i} style={{ marginBottom: i < lines.length - 1 ? '8px' : 0 }}>{l}</div>
          ))}
        </div>
      </div>

      <div style={{ display: 'flex', justifyContent: 'center', margin: '22px 0 14px' }}>
        <button
          onClick={onStart}
          style={{
            padding: '11px 22px',
            background: 'var(--accent)',
            color: 'var(--bg)',
            border: 'none',
            borderRadius: '10px',
            cursor: 'pointer',
            fontSize: '14px',
            fontWeight: 600,
          }}
        >
          Name your brain
        </button>
      </div>

      <div style={{ fontSize: '12px', color: 'var(--muted)', lineHeight: 1.7, textAlign: 'center' }}>
        <div>
          After naming, keep editing the{' '}
          <a href="/persona" style={{ color: 'var(--accent)' }}>persona document</a>
          {' '}— it is the brain's system prompt on every turn.
        </div>
        <div>Then feed it: upload writing and notes in the Knowledge tab.</div>
        <div>Every chat can be saved back into memory with Save to memory.</div>
      </div>
    </div>
  )
}

export default function Chat() {
  const [models, setModels] = useState([])
  const [selectedModel, setSelectedModel] = useState('')
  // max_tokens cap on the assistant's response. Default 2048 was causing
  // long answers to truncate mid-sentence. Operator picks a higher cap when
  // they want fuller answers; persisted server-side via /settings/max-tokens
  // so the choice survives reloads and is shared across browsers.
  const [maxTokens, setMaxTokens] = useState(2048)
  const [messages, setMessages] = useState([])
  const [inputMessage, setInputMessage] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState(null)
  const [sessions, setSessions] = useState([])
  const [currentSessionId, setCurrentSessionId] = useState(null)
  const [sidebarOpen, setSidebarOpen] = useState(true)
  // Ref to the resizable sidebar panel. Used by the chat-header toggle and
  // the in-sidebar Hide button to collapse/expand. The panel's onCollapse /
  // onExpand callbacks keep `sidebarOpen` in sync for any code that still
  // reads it (e.g. arrow direction on the toggle button).
  const sidebarPanelRef = useRef(null)
  const toggleSidebar = () => {
    const p = sidebarPanelRef.current
    if (!p) return
    if (p.isCollapsed()) p.expand()
    else p.collapse()
  }
  // On phone-width viewports default the sidebar collapsed so the message
  // column gets the full screen. Operator can still toggle via the button.
  useEffect(() => {
    if (typeof window === 'undefined') return
    if (!window.matchMedia('(max-width: 768px)').matches) return
    // Defer until the Panel ref is attached on first paint.
    const id = requestAnimationFrame(() => {
      sidebarPanelRef.current?.collapse()
    })
    return () => cancelAnimationFrame(id)
  }, [])
  const [isCreatingSession, setIsCreatingSession] = useState(false)
  const [showNameModal, setShowNameModal] = useState(false)
  const [newChatName, setNewChatName] = useState('')
  const [attachedImages, setAttachedImages] = useState([]) // [{base64, mediaType, name, dataUrl}]
  const [dragActive, setDragActive] = useState(false)
  const MAX_IMAGES = 10
  const [consolidating, setConsolidating] = useState(false)
  const [consolidateStatus, setConsolidateStatus] = useState(null) // {ok: bool, message: string} | null
  // Which memory layer "Save to memory" consolidates into (episodic / semantic
  // / procedural). Default episodic — a saved conversation is an episodic memory.
  const [saveLayer, setSaveLayer] = useState('episodic')

  // Inline session-title rename. editingSessionId == null means no row is in
  // edit mode. Enter (or blur) saves via PUT /api/bf/sessions/{id}/title;
  // Escape cancels. Pencil icon or double-click on the title starts edit.
  const [editingSessionId, setEditingSessionId] = useState(null)
  const [editingTitle, setEditingTitle] = useState('')
  const startRename = (id, currentTitle) => {
    setEditingSessionId(id)
    setEditingTitle(currentTitle || '')
  }
  const cancelRename = () => {
    setEditingSessionId(null)
    setEditingTitle('')
  }
  const saveSessionTitle = async (id) => {
    const newTitle = editingTitle.trim()
    if (!newTitle) { cancelRename(); return }
    try {
      const res = await fetch(`/api/bf/sessions/${id}/title`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: newTitle }),
      })
      if (res.ok) fetchSessions()
    } catch (e) {
      // Swallow — keep UI responsive. Operator can retry.
    }
    cancelRename()
  }

  // Theme + font: state mirrors document.documentElement.dataset. Seeded
  // from localStorage on mount; change handlers write through to both
  // dataset and localStorage so any other page picks them up on next paint.
  const [theme, setTheme] = useState('gold')
  const [font, setFont] = useState('system')
  const [scrollPace, setScrollPace] = useState('normal')
  useEffect(() => {
    if (typeof window === 'undefined') return
    setTheme(localStorage.getItem('bf-theme') || 'gold')
    const stored = localStorage.getItem('bf-font') || 'system'
    setFont(FONT_MIGRATION[stored] || stored)
    setScrollPace(localStorage.getItem('bf-scroll-pace') || 'normal')
  }, [])
  const applyScrollPace = (val) => {
    setScrollPace(val)
    if (typeof window !== 'undefined') localStorage.setItem('bf-scroll-pace', val)
  }
  const applyTheme = (val) => {
    setTheme(val)
    if (typeof window !== 'undefined') {
      localStorage.setItem('bf-theme', val)
      document.documentElement.dataset.theme = val
    }
  }
  const applyFont = (val) => {
    setFont(val)
    if (typeof window !== 'undefined') {
      localStorage.setItem('bf-font', val)
      document.documentElement.dataset.font = val
    }
  }

  const consolidateSession = async () => {
    if (!currentSessionId || consolidating) return
    if (messages.length < 2) { setConsolidateStatus({ ok: false, message: 'Chat too short to save (need at least one exchange).' }); return }
    setConsolidating(true)
    setConsolidateStatus(null)
    try {
      const permitRes = await fetch('/api/permit', { method: 'POST' })
      const permitData = await permitRes.json()
      if (!permitData.permit_id || !permitData.permit_token) {
        setConsolidateStatus({ ok: false, message: 'Permit failed — could not save.' })
        setConsolidating(false)
        return
      }
      const r = await fetch(`/api/bf/chat/sessions/${currentSessionId}/consolidate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          model: selectedModel,
          layer: saveLayer,
          permit_id: permitData.permit_id,
          permit_token: permitData.permit_token,
        }),
      })
      if (r.ok) {
        const data = await r.json()
        setConsolidateStatus({ ok: true, message: `Saved to memory: ${data.chunks_stored} chunks in the ${data.layer || saveLayer} layer.` })
      } else {
        const err = await r.json().catch(() => ({}))
        setConsolidateStatus({ ok: false, message: err.detail || `Failed (${r.status})` })
      }
    } catch (e) {
      setConsolidateStatus({ ok: false, message: e.message })
    } finally {
      setConsolidating(false)
      // auto-clear status after 6 sec
      setTimeout(() => setConsolidateStatus(null), 6000)
    }
  }

  const ingestImageFiles = (fileList) => {
    const incoming = Array.from(fileList || [])
    const onlyImages = incoming.filter(f => f.type.startsWith('image/'))
    if (incoming.length > onlyImages.length) {
      setError(`Skipped ${incoming.length - onlyImages.length} non-image file(s)`)
    }
    setAttachedImages(prev => {
      const room = MAX_IMAGES - prev.length
      if (room <= 0) {
        setError(`Already at max ${MAX_IMAGES} images — remove one to add more`)
        return prev
      }
      const accepted = onlyImages.slice(0, room).filter(f => f.size <= 5 * 1024 * 1024)
      const oversized = onlyImages.slice(0, room).length - accepted.length
      if (oversized > 0) setError(`${oversized} image(s) over 5MB — skipped`)
      if (onlyImages.length > room) setError(`Capped at ${MAX_IMAGES} images — extras ignored`)
      accepted.forEach(file => {
        const reader = new FileReader()
        reader.onload = () => {
          const dataUrl = reader.result
          const base64 = String(dataUrl).split(',')[1]
          setAttachedImages(curr => [...curr, { base64, mediaType: file.type, name: file.name, dataUrl }])
        }
        reader.onerror = () => setError(`Failed to read ${file.name}`)
        reader.readAsDataURL(file)
      })
      return prev
    })
  }

  const handleImageSelect = e => {
    ingestImageFiles(e.target.files)
    e.target.value = '' // allow re-selecting same file
  }

  const removeImageAt = (idx) => {
    setAttachedImages(prev => prev.filter((_, i) => i !== idx))
  }

  const handleChatDragOver = e => {
    e.preventDefault()
    e.stopPropagation()
    if (!dragActive) setDragActive(true)
  }
  const handleChatDragLeave = e => {
    e.preventDefault()
    e.stopPropagation()
    setDragActive(false)
  }
  const handleChatDrop = e => {
    e.preventDefault()
    e.stopPropagation()
    setDragActive(false)
    if (e.dataTransfer?.files?.length) ingestImageFiles(e.dataTransfer.files)
  }
  const messagesEndRef = useRef(null)
  const messagesContainerRef = useRef(null)
  const textareaRef = useRef(null)
  const [stickToBottom, setStickToBottom] = useState(true)

  // On touch devices the on-screen keyboard has no Shift, so Shift+Enter
  // cannot make a newline. There, plain Enter inserts a newline and the
  // Send button is the only way to send — the messaging-app convention.
  const [isTouch, setIsTouch] = useState(false)
  useEffect(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return
    const mq = window.matchMedia('(pointer: coarse)')
    const update = () => setIsTouch(mq.matches)
    update()
    mq.addEventListener?.('change', update)
    return () => mq.removeEventListener?.('change', update)
  }, [])

  // Typewriter reveal: per-session streaming buffer keyed by session id.
  // Switching sessions mid-stream no longer paints incoming tokens into the
  // wrong view (the 2026-05-18 hbar.health demo bug) — deltas always land in
  // their originating session's entry, the rAF advances all entries each
  // tick, and writeShown paints only into the view for currentSessionId.
  // Concurrent sends across sessions don't merge into one buffer.
  const revealRef = useRef(new Map()) // sessionId → { full, shown, done, last }
  const revealRafRef = useRef(null)

  // Mirror currentSessionId in a ref so the rAF closure always reads the
  // latest value without needing to be recreated on every session change.
  const currentSessionIdRef = useRef(null)

  // AbortController for the in-flight /chat/rag request. The Stop button
  // calls .abort() to cancel a streaming response mid-flight — for the
  // "brain is generating too much, I want it to stop" case. Held in a ref
  // so the button (in a different render scope from sendMessage) can reach it.
  const abortControllerRef = useRef(null)
  const stopMessage = () => {
    if (abortControllerRef.current) abortControllerRef.current.abort()
  }

  // Per-message copy-to-clipboard state. copiedIndex is the message index
  // that just had its content copied; it briefly flips to a ✓ label then
  // reverts. One-shot UX, no library, no toast system.
  const [copiedIndex, setCopiedIndex] = useState(null)
  const copyMessage = async (idx, msg) => {
    const content = typeof msg.content === 'string' ? msg.content : ''
    if (!content) return
    try {
      await navigator.clipboard.writeText(content)
      setCopiedIndex(idx)
      setTimeout(() => setCopiedIndex(prev => prev === idx ? null : prev), 1500)
    } catch {
      // Clipboard API can fail on insecure origins or if permissions denied;
      // operator sees the button click do nothing — acceptable degradation.
    }
  }

  // Hide chats — sidebar affordance to clear a session from the visible list
  // without deleting it. Persisted client-side in localStorage so it survives
  // reloads without a backend schema change. "Show hidden" toggle reveals
  // them again. Hide is reversible; only the explicit × is destructive.
  const HIDDEN_SESSIONS_KEY = 'brain_hidden_sessions'
  const [hiddenSessions, setHiddenSessions] = useState(() => {
    if (typeof window === 'undefined') return new Set()
    try {
      const raw = window.localStorage.getItem(HIDDEN_SESSIONS_KEY)
      return raw ? new Set(JSON.parse(raw)) : new Set()
    } catch { return new Set() }
  })
  const [showHidden, setShowHidden] = useState(false)
  const persistHiddenSessions = (next) => {
    try { window.localStorage.setItem(HIDDEN_SESSIONS_KEY, JSON.stringify(Array.from(next))) } catch {}
  }
  const toggleHideSession = (sid) => {
    setHiddenSessions(prev => {
      const next = new Set(prev)
      if (next.has(sid)) next.delete(sid); else next.add(sid)
      persistHiddenSessions(next)
      return next
    })
  }

  // "Store this" button state — Phase A of the memory capture flow.
  // storedMessages: indices of messages already stored (renders as ✓ Stored).
  // storingIndex: the message currently being POSTed (renders as ... saving).
  // storeError: optional error text if a store request fails.
  // Per-session reset would be cleaner but messages already remount on
  // session switch, so a Set keyed by current message index is fine.
  const [storedMessages, setStoredMessages] = useState(new Set())
  const [storingIndex, setStoringIndex] = useState(null)
  const [storeError, setStoreError] = useState(null)

  // Phase B classify-and-propose modal state. When the operator clicks
  // "store" (without shift), we open this modal, ask the brain to propose
  // {layer, path, tags, title, content, rationale}, and let the operator
  // accept / edit / reject. Shift-click stays on the raw_inbox path below
  // for "drop this fast, don't bother classifying."
  const [proposalOpen, setProposalOpen] = useState(false)
  const [proposalIdx, setProposalIdx] = useState(null)
  const [proposalLoading, setProposalLoading] = useState(false)
  const [proposalError, setProposalError] = useState(null)
  const [proposal, setProposal] = useState(null)  // original from server
  const [draft, setDraft] = useState(null)        // operator-editable copy

  // Raw-inbox path — Phase A behavior. Triggered by shift-click on store.
  const storeRawInbox = async (idx, msg) => {
    if (storedMessages.has(idx) || storingIndex !== null) return
    const content = typeof msg.content === 'string' ? msg.content.trim() : ''
    if (!content) return
    setStoringIndex(idx)
    setStoreError(null)
    try {
      const r = await fetch('/api/bf/memory/store', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          content,
          mode: 'raw_inbox',
          source: 'chat-store-button',
          session_id: currentSessionIdRef.current,
          message_role: msg.role,
        }),
      })
      if (r.ok) {
        setStoredMessages(prev => {
          const next = new Set(prev); next.add(idx); return next
        })
      } else {
        const body = await r.text().catch(() => '')
        setStoreError(`Store failed: ${r.status} ${body.slice(0, 120)}`)
      }
    } catch (e) {
      setStoreError(`Store failed: ${e.message}`)
    } finally {
      setStoringIndex(null)
    }
  }

  // Phase B default: open modal + ask brain to classify.
  const openProposalModal = async (idx, msg) => {
    if (storedMessages.has(idx) || proposalOpen) return
    const content = typeof msg.content === 'string' ? msg.content.trim() : ''
    if (!content) return
    setProposalIdx(idx)
    setProposalOpen(true)
    setProposalLoading(true)
    setProposalError(null)
    setProposal(null); setDraft(null)
    // Build a small context window — last 4 messages excluding the one being
    // stored — so the classifier has signal about what conversation this is in.
    const ctxMsgs = messages.slice(Math.max(0, idx - 4), idx)
      .map(m => `${m.role}: ${typeof m.content === 'string' ? m.content : ''}`).join('\n')
    try {
      const r = await fetch('/api/bf/memory/store/propose', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content, context: ctxMsgs, model: selectedModel }),
      })
      if (r.ok) {
        const j = await r.json()
        setProposal(j)
        setDraft({
          layer: j.layer || 'episodic',
          path: j.path || '',
          tags: (j.tags || []).join(', '),
          title: j.title || '',
          content: j.content || content,
          rationale: j.rationale || '',
        })
      } else {
        const body = await r.text().catch(() => '')
        setProposalError(`Classifier failed: ${r.status} ${body.slice(0, 200)}`)
      }
    } catch (e) {
      setProposalError(`Classifier failed: ${e.message}`)
    } finally {
      setProposalLoading(false)
    }
  }

  const closeProposalModal = () => {
    setProposalOpen(false); setProposalIdx(null); setProposal(null); setDraft(null); setProposalError(null)
  }

  const commitProposal = async (decision) => {
    if (!draft || proposalIdx === null) return
    const msg = messages[proposalIdx]
    if (!msg) return
    const tagsArr = draft.tags ? draft.tags.split(',').map(s => s.trim()).filter(Boolean) : []
    // Decision derivation: if any field differs from the original proposal,
    // the operator edited it — log as "edit", otherwise as "accept". Reject
    // is the explicit other path; reject_reason is captured separately.
    let computedDecision = decision
    if (decision === 'accept' && proposal) {
      const changed =
        draft.layer !== proposal.layer ||
        draft.path !== (proposal.path || '') ||
        draft.title !== (proposal.title || '') ||
        draft.content !== (proposal.content || '') ||
        JSON.stringify(tagsArr) !== JSON.stringify(proposal.tags || [])
      if (changed) computedDecision = 'edit'
    }
    setProposalLoading(true)
    setProposalError(null)
    try {
      const r = await fetch('/api/bf/memory/store', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          content: draft.content,
          mode: 'classified',
          source: 'chat-store-button',
          session_id: currentSessionIdRef.current,
          message_role: msg.role,
          // proposal (what the brain said)
          proposed_layer: proposal?.layer,
          proposed_path: proposal?.path,
          proposed_tags: proposal?.tags,
          proposed_title: proposal?.title,
          proposed_content: proposal?.content,
          proposed_rationale: proposal?.rationale,
          // final (what the operator committed to)
          decision: computedDecision,
          final_layer: draft.layer,
          final_path: draft.path,
        }),
      })
      if (r.ok) {
        setStoredMessages(prev => {
          const next = new Set(prev); next.add(proposalIdx); return next
        })
        closeProposalModal()
      } else {
        const body = await r.text().catch(() => '')
        setProposalError(`Store failed: ${r.status} ${body.slice(0, 200)}`)
      }
    } catch (e) {
      setProposalError(`Store failed: ${e.message}`)
    } finally {
      setProposalLoading(false)
    }
  }

  const rejectProposal = async () => {
    if (proposalIdx === null) return
    const msg = messages[proposalIdx]
    if (!msg) return
    const content = typeof msg.content === 'string' ? msg.content.trim() : ''
    setProposalLoading(true)
    setProposalError(null)
    try {
      await fetch('/api/bf/memory/store', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          content,
          decision: 'reject',
          mode: 'classified',
          source: 'chat-store-button',
          session_id: currentSessionIdRef.current,
          message_role: msg.role,
          proposed_layer: proposal?.layer,
          proposed_path: proposal?.path,
          proposed_tags: proposal?.tags,
          proposed_title: proposal?.title,
          proposed_rationale: proposal?.rationale,
        }),
      })
      closeProposalModal()
    } catch (e) {
      setProposalError(`Reject failed: ${e.message}`)
    } finally {
      setProposalLoading(false)
    }
  }

  // Dispatcher used by the per-message store button. Shift-click is the
  // fast path (raw_inbox, Phase A); plain click is the classify path (Phase B).
  const storeMessage = (idx, msg, ev) => {
    if (storedMessages.has(idx) || storingIndex !== null) return
    if (ev && (ev.shiftKey || ev.altKey)) {
      storeRawInbox(idx, msg)
    } else {
      openProposalModal(idx, msg)
    }
  }

  // Persona configuration state. /persona/status tells us whether the brain
  // is still the unedited template ([BRAIN_NAME]/[OWNER_NAME] unfilled). When
  // it is, the chat surfaces a "name your brain" onboarding flow — the
  // cold-start fix get-a-brain depends on.
  const [personaStatus, setPersonaStatus] = useState(null)
  const [showPersonalize, setShowPersonalize] = useState(false)
  const [personaBrainName, setPersonaBrainName] = useState('')
  const [personaOwnerName, setPersonaOwnerName] = useState('')
  const [personalizing, setPersonalizing] = useState(false)
  const [personaError, setPersonaError] = useState(null)

  const personaUnconfigured = personaStatus && personaStatus.configured === false

  const personalizeBrain = async () => {
    const brainName = personaBrainName.trim()
    const ownerName = personaOwnerName.trim()
    if (!brainName || !ownerName) { setPersonaError('Both a brain name and an owner name are required.'); return }
    setPersonalizing(true)
    setPersonaError(null)
    try {
      const r = await fetch('/api/bf/persona/personalize', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ brain_name: brainName, owner_name: ownerName }),
      })
      if (r.ok) {
        setPersonaStatus({ configured: true, is_template: false, placeholders: [] })
        setShowPersonalize(false)
        setPersonaBrainName('')
        setPersonaOwnerName('')
      } else {
        const err = await r.json().catch(() => ({}))
        setPersonaError(err.detail || `Failed (${r.status})`)
      }
    } catch (e) {
      setPersonaError(e.message)
    } finally {
      setPersonalizing(false)
    }
  }

  // Wrap the current textarea selection in markdown markers (toolbar buttons +
  // Cmd/Ctrl-B / -I / -E shortcuts). The composer stays plain markdown text —
  // no rich-text model — so typing **x** by hand works identically.
  const applyMarkdown = (before, after = before) => {
    const ta = textareaRef.current
    if (!ta) return
    const start = ta.selectionStart ?? inputMessage.length
    const end = ta.selectionEnd ?? inputMessage.length
    const selected = inputMessage.slice(start, end)
    const next = inputMessage.slice(0, start) + before + selected + after + inputMessage.slice(end)
    setInputMessage(next)
    // Restore a sensible selection after React re-renders the textarea: keep
    // the wrapped text selected, or drop the caret between the markers.
    requestAnimationFrame(() => {
      ta.focus()
      if (selected) ta.setSelectionRange(start + before.length, end + before.length)
      else { const caret = start + before.length; ta.setSelectionRange(caret, caret) }
    })
  }

  // Prefix the current line — or every line the selection touches — with a
  // markdown marker (the List toolbar button: "- "). Line-level, not a wrap;
  // the composer stays plain markdown. Lines already prefixed are left alone.
  const applyLinePrefix = (prefix) => {
    const ta = textareaRef.current
    if (!ta) return
    const val = inputMessage
    const selStart = ta.selectionStart ?? val.length
    const selEnd = ta.selectionEnd ?? val.length
    const lineStart = val.lastIndexOf('\n', selStart - 1) + 1
    let lineEnd = val.indexOf('\n', selEnd)
    if (lineEnd === -1) lineEnd = val.length
    const prefixed = val.slice(lineStart, lineEnd)
      .split('\n')
      .map(l => (l.startsWith(prefix) ? l : prefix + l))
      .join('\n')
    const next = val.slice(0, lineStart) + prefixed + val.slice(lineEnd)
    setInputMessage(next)
    requestAnimationFrame(() => {
      ta.focus()
      ta.setSelectionRange(lineStart, lineStart + prefixed.length)
    })
  }

  useEffect(() => {
    loadModelsAndDefault()
      .then(({ models, default: def }) => { setModels(models); setSelectedModel(def) })
      .catch(e => setError(`Models: ${e.message}`))

    fetch('/api/bf/settings/max-tokens')
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d && typeof d.max_tokens === 'number') setMaxTokens(d.max_tokens) })
      .catch(() => {})

    fetchSessions()

    // Is the brain still the unconfigured template? Drives the onboarding flow.
    fetch('/api/bf/persona/status')
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d) setPersonaStatus(d) })
      .catch(() => {})
  }, [])

  // Scroll-along: while sticking to bottom, creep toward the latest content
  // at the operator's chosen pace (instant / slow / normal / fast). When
  // content grows more than a viewport ahead, accelerate proportionally so
  // we don't fall absurdly behind. The rAF reads scrollHeight every frame.
  useEffect(() => {
    if (!stickToBottom) return
    const c = messagesContainerRef.current
    if (!c) return
    const paceObj = SCROLL_PACE_OPTIONS.find(p => p.value === scrollPace) || SCROLL_PACE_OPTIONS[2]
    const pace = paceObj.pxPerFrame
    let raf
    const tick = () => {
      const target = c.scrollHeight - c.clientHeight
      const dist = target - c.scrollTop
      if (dist > 0) {
        if (pace === Infinity) {
          c.scrollTop = target
        } else {
          const step = dist > c.clientHeight
            ? Math.max(pace * 1.4, dist * 0.05)
            : pace
          c.scrollTop = Math.min(target, c.scrollTop + step)
        }
      }
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [stickToBottom, scrollPace])

  const fetchSessions = () => {
    fetch('/api/bf/sessions')
      .then(r => r.ok ? r.json() : null)
      .then(d => {
        // Only update state if the response is a confirmed array.
        // Don't wipe sidebar on malformed/empty/transient responses.
        if (d && Array.isArray(d.sessions)) {
          setSessions(d.sessions)
        } else if (d) {
          console.warn('sessions response missing sessions array:', d)
        }
      })
      .catch(console.error)
  }

  const loadSessionMessages = sessionId => {
    fetch(`/api/bf/sessions/${sessionId}/messages`)
      .then(r => r.ok ? r.json() : null)
      .then(d => {
        if (!d) return
        // Same defensive pattern as fetchSessions — don't wipe messages
        // on malformed responses. Only update if messages is a real array.
        if (Array.isArray(d.messages)) {
          setMessages(d.messages)
          setCurrentSessionId(sessionId)
        } else {
          console.warn('messages response missing messages array:', d)
        }
      })
      .catch(console.error)
  }

  const createNewSession = async (title = 'New Chat') => {
    if (!selectedModel) { setError('Select a model first'); return }
    setIsCreatingSession(true)
    try {
      const r = await fetch('/api/bf/sessions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model_name: selectedModel, title }),
      })
      if (r.ok) {
        const s = await r.json()
        setCurrentSessionId(s.session_id)
        setMessages([])
        fetchSessions()
      }
    } catch (e) {
      setError('Failed to create session')
    } finally {
      setIsCreatingSession(false)
    }
  }

  const deleteSession = async sessionId => {
    try {
      const r = await fetch(`/api/bf/sessions/${sessionId}`, { method: 'DELETE' })
      if (r.ok) {
        if (currentSessionId === sessionId) { setCurrentSessionId(null); setMessages([]) }
        fetchSessions()
      }
    } catch (e) {
      setError('Failed to delete session')
    }
  }

  const sendMessage = async () => {
    if (!inputMessage.trim() || !selectedModel || isLoading) return

    setStickToBottom(true)

    let sessionId = currentSessionId
    if (!sessionId) {
      setIsCreatingSession(true)
      try {
        const r = await fetch('/api/bf/sessions', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ model_name: selectedModel, title: 'New Chat' }),
        })
        if (r.ok) {
          const s = await r.json()
          sessionId = s.session_id
          setCurrentSessionId(sessionId)
          fetchSessions()
        }
      } catch (e) {
        setError('Failed to create session')
        setIsCreatingSession(false)
        return
      }
      setIsCreatingSession(false)
    }

    const userMessage = {
      role: 'user',
      content: inputMessage.trim(),
      imageDataUrls: attachedImages.map(i => i.dataUrl), // local render only, not sent to backend
    }
    const updated = [...messages, userMessage]
    const imagesForRequest = attachedImages // capture before clearing
    setMessages(updated)
    setInputMessage('')
    setAttachedImages([])
    setIsLoading(true)
    setError(null)
    const useStreaming = imagesForRequest.length === 0 // vision path is non-streaming in v0.7

    // Create the AbortController BEFORE any await so there's no window where
    // the Stop button is visible but the controller hasn't been initialized
    // yet (which would make the click a no-op). Both the permit and chat/rag
    // fetches share this controller — Stop aborts whichever is in flight.
    abortControllerRef.current = new AbortController()
    const abortSignal = abortControllerRef.current.signal

    try {
      const permitRes = await fetch('/api/permit', { method: 'POST', signal: abortSignal })
      const permitData = await permitRes.json()
      if (!permitData.permit_id || !permitData.permit_token) {
        setError(`Permit failed: ${permitData.detail || permitData.error || 'NodeOS did not issue permit'}`)
        setIsLoading(false)
        return
      }

      // Strip image data URLs from messages sent to backend — server doesn't need them
      // and they'd bloat the request.
      const messagesForBackend = updated.map(m => {
        const { imageDataUrls, ...rest } = m
        return rest
      })

      const r = await fetch('/api/bf/chat/rag', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        signal: abortSignal,
        body: JSON.stringify({
          model: selectedModel,
          messages: messagesForBackend,
          session_id: sessionId,
          layers: ['identity', 'thinking', 'projects', 'writing', 'episodic'],
          search_limit: 5,
          stream: useStreaming,
          max_tokens: maxTokens,
          ...(imagesForRequest.length > 0 ? {
            images: imagesForRequest.map(i => ({ base64: i.base64, media_type: i.mediaType })),
          } : {}),
          permit_id: permitData.permit_id,
          permit_token: permitData.permit_token,
        }),
      })

      if (!r.ok) {
        const err = await r.json().catch(() => ({}))
        setError(`Error ${r.status}: ${err.detail || 'server error — check API logs'}`)
      } else if (!useStreaming) {
        // Vision path returns JSON
        const data = await r.json()
        setMessages([...updated, { role: 'assistant', content: data.choices[0].message.content }])
        fetchSessions()
      } else {
        // Streaming path — consume SSE into a typewriter buffer. Deltas land
        // in revealRef.full the moment they arrive; a rAF reveals them at the
        // chosen cps, turning the provider's bursty stream into a calm, even
        // reading cadence. 'instant' pace skips the typewriter entirely.
        setMessages([...updated, { role: 'assistant', content: '' }])

        const paceObj = SCROLL_PACE_OPTIONS.find(p => p.value === scrollPace) || SCROLL_PACE_OPTIONS[2]
        const cps = paceObj.cps

        // Create a per-session buffer for this stream. Other in-flight streams
        // (e.g. a concurrent send to another session) keep their own buffers.
        revealRef.current.set(sessionId, { full: '', shown: 0, done: false, last: 0 })

        // Paint into the message list only when the originating session is the
        // one currently in view. In-flight tokens for a session the user has
        // switched away from sit in their buffer; when the stream completes,
        // the saved assistant message becomes visible the next time that
        // session is opened (via its history fetch).
        const writeShown = (sid) => {
          if (sid !== currentSessionIdRef.current) return
          const st = revealRef.current.get(sid)
          if (!st) return
          const text = st.full.slice(0, Math.floor(st.shown))
          setMessages(prev => {
            const next = [...prev]
            next[next.length - 1] = { role: 'assistant', content: text }
            return next
          })
        }

        // One rAF advances every active stream's buffer; only the visible
        // session's content is painted into the DOM. Idle entries are
        // garbage-collected once done && fully drained.
        const reveal = ts => {
          let anyActive = false
          for (const [sid, st] of revealRef.current.entries()) {
            if (cps === Infinity) {
              st.shown = st.full.length
            } else {
              if (!st.last) st.last = ts
              const dt = Math.min(0.25, (ts - st.last) / 1000) // clamp tab-away jumps
              st.last = ts
              const behind = st.full.length - st.shown
              // Accelerate when far behind so a slow pace can't strand the
              // reader minutes behind a long answer.
              const rate = behind > 400 ? cps * (1 + behind / 400) : cps
              st.shown = Math.min(st.full.length, st.shown + rate * dt)
            }
            writeShown(sid)
            if (st.done && st.shown >= st.full.length) {
              revealRef.current.delete(sid)
            } else {
              anyActive = true
            }
          }
          if (anyActive) {
            revealRafRef.current = requestAnimationFrame(reveal)
          } else {
            revealRafRef.current = null
          }
        }
        if (!revealRafRef.current) {
          revealRafRef.current = requestAnimationFrame(reveal)
        }

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
            const data = frame.slice(6).trim()
            if (data === '[DONE]') continue
            try {
              const parsed = JSON.parse(data)
              const delta = parsed.choices?.[0]?.delta?.content
              if (delta) {
                const st = revealRef.current.get(sessionId)
                if (st) st.full += delta
              }
              else if (parsed.error) setError(`Stream error: ${parsed.error}`)
            } catch {
              // Skip malformed frames silently.
            }
          }
        }
        // Stream finished — let the reveal loop drain the remaining buffer.
        const st = revealRef.current.get(sessionId)
        if (st) st.done = true
        fetchSessions()
      }
    } catch (e) {
      // Stop button abort: not an error — but the network-level abort alone
      // isn't enough. New tokens stop arriving, but the typewriter keeps
      // revealing whatever's already in the buffer at the configured cps,
      // so the visible text keeps growing until the buffer drains. From
      // the operator's perspective the Stop button "didn't stop" anything.
      // Snap shown = full.length on abort so the message instantly settles
      // at its current state and visible growth halts the moment Stop fires.
      if (e.name === 'AbortError') {
        const st = revealRef.current.get(sessionId)
        if (st) { st.shown = st.full.length; st.done = true }
        fetchSessions()
      } else {
        setError(`Network error: ${e.message}`)
      }
    } finally {
      setIsLoading(false)
      abortControllerRef.current = null
    }
  }

  const handleKeyDown = e => {
    // Cmd/Ctrl-B / -I / -E wrap the current selection in markdown markers.
    if ((e.metaKey || e.ctrlKey) && !e.shiftKey && !e.altKey) {
      const k = e.key.toLowerCase()
      if (k === 'b') { e.preventDefault(); applyMarkdown('**'); return }
      if (k === 'i') { e.preventDefault(); applyMarkdown('*'); return }
      if (k === 'e') { e.preventDefault(); applyMarkdown('`'); return }
    }
    // Enter sends; Shift-Enter inserts a newline. On touch devices there
    // is no Shift, so plain Enter falls through to a newline and the Send
    // button is the only way to send.
    if (e.key === 'Enter' && !e.shiftKey && !isTouch) { e.preventDefault(); sendMessage() }
  }

  // Cancel any in-flight typewriter rAF when the page unmounts.
  useEffect(() => () => {
    if (revealRafRef.current) cancelAnimationFrame(revealRafRef.current)
  }, [])

  // Keep the rAF-readable mirror of currentSessionId fresh so streams paint
  // into the right view as the user navigates between sessions.
  useEffect(() => { currentSessionIdRef.current = currentSessionId }, [currentSessionId])

  const formatDate = dateString => {
    if (!dateString) return ''
    const d = new Date(dateString)
    const diff = Math.floor((Date.now() - d) / 86400000)
    if (diff === 0) return 'Today'
    if (diff === 1) return 'Yesterday'
    if (diff < 7) return `${diff}d ago`
    return d.toLocaleDateString()
  }

  return (
    <>
    <PanelGroup
      direction="horizontal"
      autoSaveId="bf-chat-panels"
      style={{
        // Subtract nav height (52px content + PWA safe-area-top) so the
        // chat column fills exactly the viewport below the nav.
        height: 'calc(100vh - 52px - env(safe-area-inset-top, 0px))',
        backgroundColor: 'var(--bg)',
        color: 'var(--text)',
        fontFamily: 'var(--font-body)',
      }}
    >

      {/* Sidebar — drag the handle to resize, double-click to collapse,
          or click the toggle in the chat header / footer button. */}
      <Panel
        ref={sidebarPanelRef}
        collapsible
        collapsedSize={0}
        defaultSize={22}
        minSize={15}
        maxSize={40}
        onCollapse={() => setSidebarOpen(false)}
        onExpand={() => setSidebarOpen(true)}
        style={{
          backgroundColor: 'var(--surface)',
          borderRight: '1px solid var(--border)',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
        }}
      >
        <div style={{
          padding: '16px',
          borderBottom: '1px solid var(--border)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexShrink: 0,
        }}>
          <span style={{ fontSize: '11px', fontWeight: '600', color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.1em' }}>
            Sessions
          </span>
          <button
            onClick={() => { setNewChatName(''); setShowNameModal(true) }}
            disabled={isCreatingSession || !selectedModel}
            style={{
              background: 'var(--accent)',
              color: 'var(--bg)',
              border: 'none',
              borderRadius: '6px',
              padding: '5px 10px',
              fontSize: '13px',
              cursor: isCreatingSession || !selectedModel ? 'not-allowed' : 'pointer',
              opacity: isCreatingSession || !selectedModel ? 0.4 : 1,
            }}
          >
            + New
          </button>
        </div>

        {/* Show-hidden toggle. Only renders when there's at least one hidden
            session, so the affordance is invisible until it has a purpose.
            Click flips the filter; the count next to it makes the off-state
            useful as a passive "how much have I tucked away" indicator. */}
        {hiddenSessions.size > 0 && (
          <div style={{ padding: '6px 12px', borderBottom: '1px solid var(--border)', fontSize: '11px' }}>
            <button
              onClick={() => setShowHidden(v => !v)}
              style={{ background: 'transparent', border: 'none', color: 'var(--muted)', cursor: 'pointer', padding: 0, fontSize: '11px', fontFamily: 'inherit' }}
              onMouseOver={e => e.currentTarget.style.color = 'var(--accent)'}
              onMouseOut={e => e.currentTarget.style.color = 'var(--muted)'}
            >
              {showHidden ? '▾' : '▸'} {showHidden ? 'hiding' : 'show'} hidden ({hiddenSessions.size})
            </button>
          </div>
        )}

        <div style={{ flex: 1, overflowY: 'auto', padding: '8px' }}>
          {(() => {
            // Sessions list is filtered against the hidden Set unless the
            // operator has clicked "show hidden" — same render path either
            // way, so the per-row hide/show button only needs to flip the
            // Set in localStorage.
            const visibleSessions = showHidden
              ? sessions
              : sessions.filter(s => !hiddenSessions.has(s.session_id))
            if (sessions.length === 0) {
              return (
                <div style={{ textAlign: 'center', padding: '40px 16px' }}>
                  <div style={{ fontSize: '22px', marginBottom: '8px', color: 'var(--accent)', opacity: 0.4 }}>ℏ</div>
                  <div style={{ fontSize: '12px', color: 'var(--muted)', lineHeight: 1.6 }}>No sessions yet.<br />Click + New to begin.</div>
                </div>
              )
            }
            if (visibleSessions.length === 0) {
              return (
                <div style={{ textAlign: 'center', padding: '40px 16px' }}>
                  <div style={{ fontSize: '12px', color: 'var(--muted)', lineHeight: 1.6 }}>All {sessions.length} sessions are hidden.<br />Click "show hidden" above to reveal.</div>
                </div>
              )
            }
            return visibleSessions.map(s => (
              <div
                key={s.session_id}
                onClick={() => loadSessionMessages(s.session_id)}
                style={{
                  padding: '10px 12px',
                  margin: '2px 0',
                  borderRadius: '8px',
                  cursor: 'pointer',
                  backgroundColor: currentSessionId === s.session_id ? 'rgba(201,169,110,0.1)' : 'transparent',
                  border: `1px solid ${currentSessionId === s.session_id ? 'rgba(201,169,110,0.2)' : 'transparent'}`,
                  transition: 'all 0.15s ease',
                }}
                onMouseOver={e => { if (currentSessionId !== s.session_id) e.currentTarget.style.backgroundColor = 'var(--surface2)' }}
                onMouseOut={e => { if (currentSessionId !== s.session_id) e.currentTarget.style.backgroundColor = 'transparent' }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '4px', gap: '4px' }}>
                  {editingSessionId === s.session_id ? (
                    <input
                      autoFocus
                      value={editingTitle}
                      onChange={e => setEditingTitle(e.target.value)}
                      onClick={e => e.stopPropagation()}
                      onKeyDown={e => {
                        if (e.key === 'Enter') { e.preventDefault(); saveSessionTitle(s.session_id) }
                        else if (e.key === 'Escape') { e.preventDefault(); cancelRename() }
                      }}
                      onBlur={() => saveSessionTitle(s.session_id)}
                      style={{
                        flex: 1,
                        fontSize: '13px',
                        fontWeight: '500',
                        padding: '2px 6px',
                        border: '1px solid var(--accent)',
                        borderRadius: '4px',
                        background: 'var(--bg)',
                        color: 'var(--text)',
                        outline: 'none',
                        fontFamily: 'inherit',
                        minWidth: 0,
                      }}
                    />
                  ) : (
                    <div
                      onDoubleClick={e => { e.stopPropagation(); startRename(s.session_id, s.title) }}
                      title="Double-click to rename"
                      style={{ fontSize: '13px', fontWeight: '500', color: 'var(--text)', flex: 1, marginRight: '4px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                    >
                      {s.title || 'Untitled'}
                    </div>
                  )}
                  {editingSessionId !== s.session_id && (
                    <>
                      <button
                        onClick={e => { e.stopPropagation(); startRename(s.session_id, s.title) }}
                        title="Rename"
                        style={{ background: 'none', border: 'none', color: 'var(--muted)', cursor: 'pointer', fontSize: '13px', padding: '0 2px', lineHeight: 1, flexShrink: 0 }}
                        onMouseOver={e => e.currentTarget.style.color = 'var(--accent)'}
                        onMouseOut={e => e.currentTarget.style.color = 'var(--muted)'}
                      >
                        ✎
                      </button>
                      <button
                        onClick={e => { e.stopPropagation(); toggleHideSession(s.session_id) }}
                        title={hiddenSessions.has(s.session_id) ? 'Unhide' : 'Hide from sidebar'}
                        style={{ background: 'none', border: 'none', color: 'var(--muted)', cursor: 'pointer', fontSize: '13px', padding: '0 2px', lineHeight: 1, flexShrink: 0 }}
                        onMouseOver={e => e.currentTarget.style.color = 'var(--accent)'}
                        onMouseOut={e => e.currentTarget.style.color = 'var(--muted)'}
                      >
                        {hiddenSessions.has(s.session_id) ? '↻' : '⊘'}
                      </button>
                      <button
                        onClick={e => { e.stopPropagation(); deleteSession(s.session_id) }}
                        title="Delete"
                        style={{ background: 'none', border: 'none', color: 'var(--muted)', cursor: 'pointer', fontSize: '16px', padding: '0 2px', lineHeight: 1, flexShrink: 0 }}
                        onMouseOver={e => e.currentTarget.style.color = '#c96e6e'}
                        onMouseOut={e => e.currentTarget.style.color = 'var(--muted)'}
                      >
                        ×
                      </button>
                    </>
                  )}
                </div>
                <div style={{ fontSize: '11px', color: 'var(--muted)' }}>
                  {s.message_count || 0} msgs &middot; {formatDate(s.created_at)}
                  {hiddenSessions.has(s.session_id) && <span style={{ marginLeft: 8, opacity: 0.6 }}>· hidden</span>}
                </div>
              </div>
            ))
          })()}
        </div>

        <div style={{
          padding: '10px 12px',
          borderTop: '1px solid var(--border)',
          flexShrink: 0,
        }}>
          <button
            onClick={() => sidebarPanelRef.current?.collapse()}
            style={{
              width: '100%',
              background: 'none',
              border: '1px solid var(--border)',
              color: 'var(--muted)',
              padding: '8px 10px',
              borderRadius: '6px',
              cursor: 'pointer',
              fontSize: '12px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '8px',
            }}
            onMouseOver={e => { e.currentTarget.style.backgroundColor = 'var(--surface2)'; e.currentTarget.style.color = 'var(--text)' }}
            onMouseOut={e => { e.currentTarget.style.backgroundColor = 'transparent'; e.currentTarget.style.color = 'var(--muted)' }}
          >
            <span>◀</span>
            <span>Hide sidebar</span>
          </button>
        </div>
      </Panel>

      <PanelResizeHandle className="bf-resize-handle" />

      {/* Main */}
      <Panel defaultSize={78} style={{ display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>

        {/* Chat header */}
        <div style={{
          backgroundColor: 'var(--surface)',
          borderBottom: '1px solid var(--border)',
          padding: '12px 20px',
          display: 'flex',
          alignItems: 'center',
          gap: '12px',
          flexShrink: 0,
        }}>
          <button
            onClick={toggleSidebar}
            title={sidebarOpen ? 'Collapse sidebar' : 'Show sidebar'}
            style={{ background: 'none', border: '1px solid var(--border)', color: 'var(--muted)', padding: '6px 10px', borderRadius: '6px', cursor: 'pointer', fontSize: '13px' }}
          >
            {sidebarOpen ? '◀' : '▶'}
          </button>

          <CustomSelect
            value={selectedModel}
            onChange={(name) => { setSelectedModel(name); persistModelChoice(name) }}
            title="Model"
            minWidth={180}
            options={[
              { value: '', label: 'Select model' },
              ...models.map(m => ({
                value: m.name,
                label: m.name + (m.size ? ` (${(m.size / 1e9).toFixed(1)}GB)` : ''),
              })),
            ]}
          />

          {/* Max-tokens cap on the assistant's response. Operator picks a
              higher value when long answers were truncating; persisted
              server-side via /settings/max-tokens so reloads + other browser
              tabs honor the choice. */}
          <CustomSelect
            value={String(maxTokens)}
            onChange={(v) => {
              const n = parseInt(v, 10)
              if (!isNaN(n)) {
                setMaxTokens(n)
                fetch('/api/bf/settings/max-tokens', {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({ max_tokens: n }),
                }).catch(() => {})
              }
            }}
            title="Max response length (tokens)"
            minWidth={90}
            options={[
              { value: '256',   label: '256 (terse)' },
              { value: '512',   label: '512 (brief)' },
              { value: '1024',  label: '1k tokens' },
              { value: '2048',  label: '2k tokens' },
              { value: '4096',  label: '4k tokens' },
              { value: '8192',  label: '8k tokens' },
              { value: '16384', label: '16k tokens' },
              { value: '32768', label: '32k tokens' },
              { value: '65536', label: '64k tokens' },
            ]}
          />

          <CustomSelect
            value={theme}
            onChange={applyTheme}
            title="Theme"
            minWidth={120}
            options={THEME_OPTIONS}
          />

          <CustomSelect
            value={font}
            onChange={applyFont}
            title="Font"
            minWidth={160}
            options={FONT_OPTIONS}
          />

          <CustomSelect
            value={scrollPace}
            onChange={applyScrollPace}
            title="Reading pace — scroll speed + text-reveal cadence while streaming"
            minWidth={130}
            options={SCROLL_PACE_OPTIONS}
          />

          {currentSessionId && messages.length >= 2 && (
            <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: '8px' }}>
              {/* Memory layer this chat consolidates into — episodic / semantic
                  / procedural. The status line confirms where it landed. */}
              <CustomSelect
                value={saveLayer}
                onChange={setSaveLayer}
                title="Which memory layer Save to memory consolidates this chat into"
                minWidth={124}
                options={[
                  { value: 'episodic', label: 'episodic' },
                  { value: 'semantic', label: 'semantic' },
                  { value: 'procedural', label: 'procedural' },
                ]}
              />
              <button
                onClick={consolidateSession}
                disabled={consolidating}
                title="Save this conversation into your brain's long-term memory, in the selected layer. Future chats retrieve from it via RAG."
                style={{
                  padding: '8px 14px',
                  background: consolidating ? 'var(--surface)' : 'transparent',
                  color: consolidating ? 'var(--muted)' : 'var(--accent)',
                  border: '1px solid rgba(201, 169, 110, 0.38)',
                  borderRadius: '8px',
                  cursor: consolidating ? 'wait' : 'pointer',
                  fontSize: '12px',
                  fontFamily: 'var(--font-mono)',
                  letterSpacing: '0.04em',
                }}
              >
                {consolidating ? 'saving...' : 'Save to memory'}
              </button>
            </div>
          )}
        </div>

        {consolidateStatus && (
          <div style={{
            padding: '8px 20px',
            backgroundColor: consolidateStatus.ok ? '#1e3a26' : '#3a1e1e',
            color: consolidateStatus.ok ? '#7fc99c' : '#c98080',
            fontSize: '12px',
            borderBottom: '1px solid var(--border)',
            fontFamily: 'var(--font-mono)',
          }}>
            {consolidateStatus.message}
          </div>
        )}

        {/* Vertical split — drag the handle below the messages list to
            allocate any chunk of the column to the composer. autoSaveId
            persists sizes per browser. */}
        <PanelGroup direction="vertical" autoSaveId="bf-chat-main-vertical" style={{ flex: 1, overflow: 'hidden' }}>
        <Panel defaultSize={78} minSize={20} style={{ display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>

        {/* Messages — also the drop zone for images */}
        <div
          ref={messagesContainerRef}
          onScroll={e => {
            const el = e.currentTarget
            const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80
            setStickToBottom(nearBottom)
          }}
          onDragOver={handleChatDragOver}
          onDragLeave={handleChatDragLeave}
          onDrop={handleChatDrop}
          style={{
            flex: 1,
            overflowY: 'auto',
            padding: '24px 28px',
            display: 'flex',
            flexDirection: 'column',
            gap: '16px',
            position: 'relative',
            outline: dragActive ? '2px dashed var(--accent)' : 'none',
            outlineOffset: '-12px',
            backgroundColor: dragActive ? 'rgba(201,169,110,0.04)' : 'transparent',
            transition: 'background 0.15s ease',
          }}
        >
          {/* In-chat notice while the brain is still the unconfigured
              template — visible once a conversation is already underway. */}
          {personaUnconfigured && messages.length > 0 && (
            <div style={{
              display: 'flex', alignItems: 'center', gap: '12px',
              padding: '10px 14px',
              background: 'rgba(201,169,110,0.08)',
              border: '1px solid rgba(201,169,110,0.28)',
              borderRadius: '10px',
              fontSize: '12px',
              color: 'var(--text)',
            }}>
              <span style={{ flex: 1 }}>This brain hasn't been named yet — it's still running the template persona.</span>
              <button
                onClick={() => { setPersonaError(null); setShowPersonalize(true) }}
                style={{
                  flexShrink: 0,
                  padding: '6px 12px',
                  background: 'var(--accent)', color: 'var(--bg)',
                  border: 'none', borderRadius: '7px', cursor: 'pointer',
                  fontSize: '12px', fontWeight: 600,
                }}
              >
                Name your brain
              </button>
            </div>
          )}

          {messages.length === 0 && (
            personaUnconfigured ? (
              <IdentityOnboarding onStart={() => { setPersonaError(null); setShowPersonalize(true) }} />
            ) : (
              <div style={{ textAlign: 'center', marginTop: '100px' }}>
                <div style={{ fontSize: '32px', marginBottom: '20px', color: 'var(--accent)', opacity: 0.25 }}>ℏ</div>
                <div style={{
                  fontFamily: 'var(--font-display)',
                  fontStyle: 'italic',
                  fontSize: '17px',
                  color: 'var(--muted)',
                  letterSpacing: '0.01em',
                }}>
                  {currentSessionId ? 'Session ready.' : `${process.env.NEXT_PUBLIC_BRAIN_NAME || 'Your brain'} is ready.`}
                </div>
              </div>
            )
          )}

          {messages.map((msg, i) => (
            <div key={i} style={{ display: 'flex', justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start' }}>
              <div style={{
                maxWidth: '72%',
                padding: '14px 18px',
                borderRadius: '16px',
                background: msg.role === 'user' ? 'var(--user-bg)' : 'var(--assistant-bg)',
                color: msg.role === 'user' ? 'var(--user-text)' : 'var(--assistant-text)',
                border: msg.role === 'user' ? 'none' : '1px solid var(--border)',
                fontSize: '14px',
                lineHeight: '1.6',
                whiteSpace: msg.role === 'user' ? 'pre-wrap' : 'normal',
                wordBreak: 'break-word',
              }}>
                <div style={{ fontSize: '11px', opacity: 0.6, marginBottom: '6px', fontWeight: '500' }}>
                  {msg.role === 'user' ? 'You' : (selectedModel || 'Brain')}
                </div>
                {msg.imageDataUrls && msg.imageDataUrls.length > 0 && (
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginBottom: '8px' }}>
                    {msg.imageDataUrls.map((url, ii) => (
                      <img
                        key={ii}
                        src={url}
                        alt={`attached ${ii + 1}`}
                        style={{ maxWidth: '160px', maxHeight: 160, objectFit: 'cover', borderRadius: '8px', display: 'block' }}
                      />
                    ))}
                  </div>
                )}
                {/* User messages now render through MessageRenderer too, so
                    markdown the operator types (Cmd-B / Cmd-I shortcuts, the
                    composer's B/I toolbar) actually renders as bold/italic in
                    the sent bubble. Previously user content was raw pre-wrap
                    text and markdown markers were visible verbatim. */}
                <MessageRenderer content={msg.content} />

                {/* Footer row: Store + Copy buttons. Both are small and sit
                    below the content. Store writes to brain memory + the
                    Phase-3 feedback log; Copy puts the content on the clipboard
                    with a brief ✓ confirmation. */}
                {typeof msg.content === 'string' && msg.content.trim() && (
                  <div style={{
                    marginTop: '8px',
                    paddingTop: '8px',
                    borderTop: '1px solid var(--border)',
                    display: 'flex',
                    justifyContent: 'flex-end',
                    gap: '12px',
                    fontSize: '11px',
                    opacity: 0.5,
                  }}>
                    {copiedIndex === i ? (
                      <span title="Copied to clipboard" style={{ color: 'var(--accent)' }}>
                        ✓ copied
                      </span>
                    ) : (
                      <button
                        onClick={() => copyMessage(i, msg)}
                        title="Copy this message to clipboard"
                        style={{
                          background: 'transparent',
                          border: 'none',
                          color: 'var(--muted)',
                          cursor: 'pointer',
                          padding: '0',
                          fontSize: '11px',
                          fontFamily: 'inherit',
                          textTransform: 'lowercase',
                          letterSpacing: '0.04em',
                        }}
                        onMouseOver={e => e.currentTarget.style.color = 'var(--accent)'}
                        onMouseOut={e => e.currentTarget.style.color = 'var(--muted)'}
                      >
                        copy
                      </button>
                    )}
                    {storedMessages.has(i) ? (
                      <span title="Saved to your brain's memory" style={{ color: 'var(--accent)' }}>
                        ✓ Stored
                      </span>
                    ) : storingIndex === i ? (
                      <span style={{ color: 'var(--muted)' }}>saving…</span>
                    ) : (
                      <button
                        onClick={(e) => storeMessage(i, msg, e)}
                        disabled={storingIndex !== null || proposalOpen}
                        title="Click: classify and store (Phase B). Shift+click: raw drop, skip the modal."
                        style={{
                          background: 'transparent',
                          border: 'none',
                          color: 'var(--muted)',
                          cursor: storingIndex !== null ? 'wait' : 'pointer',
                          padding: '0',
                          fontSize: '11px',
                          fontFamily: 'inherit',
                          textTransform: 'lowercase',
                          letterSpacing: '0.04em',
                        }}
                        onMouseOver={e => { if (storingIndex === null) e.currentTarget.style.color = 'var(--accent)' }}
                        onMouseOut={e => { e.currentTarget.style.color = 'var(--muted)' }}
                      >
                        store ↗
                      </button>
                    )}
                  </div>
                )}
              </div>
            </div>
          ))}

          {isLoading && (
            <div style={{ display: 'flex', justifyContent: 'flex-start' }}>
              <div style={{ padding: '14px 18px', borderRadius: '16px', backgroundColor: 'var(--surface)', border: '1px solid var(--border)', color: 'var(--muted)', fontSize: '14px' }}>
                <div style={{ fontSize: '11px', opacity: 0.6, marginBottom: '6px' }}>{selectedModel || 'Brain'}</div>
                <span>thinking...</span>
              </div>
            </div>
          )}

          {storeError && (
            <div style={{ backgroundColor: '#1a0a0a', border: '1px solid #ff6b6b20', borderRadius: '10px', padding: '12px 16px', color: '#ff6b6b', fontSize: '13px' }}>
              {storeError}
              <button onClick={() => setStoreError(null)} style={{ float: 'right', background: 'transparent', border: 'none', color: '#ff6b6b', cursor: 'pointer' }}>×</button>
            </div>
          )}

          {error && (
            <div style={{ backgroundColor: '#1a0a0a', border: '1px solid #ff6b6b20', borderRadius: '10px', padding: '12px 16px', color: '#ff6b6b', fontSize: '13px' }}>
              {error}
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {!stickToBottom && (
          <div style={{
            display: 'flex',
            justifyContent: 'center',
            padding: '6px 0',
            backgroundColor: 'var(--bg)',
            borderTop: '1px solid var(--border)',
            flexShrink: 0,
          }}>
            <button
              onClick={() => {
                setStickToBottom(true)
                const c = messagesContainerRef.current
                if (c) c.scrollTop = c.scrollHeight
              }}
              style={{
                background: 'var(--surface)',
                border: '1px solid var(--border)',
                color: 'var(--accent)',
                padding: '6px 14px',
                borderRadius: '999px',
                cursor: 'pointer',
                fontSize: '12px',
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
              }}
            >
              <span>↓</span>
              <span>Jump to latest</span>
            </button>
          </div>
        )}

        </Panel>

        <PanelResizeHandle className="bf-resize-handle bf-resize-handle--horizontal" />

        <Panel defaultSize={22} minSize={10} maxSize={70} style={{ display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>

        {/* Input */}
        <div className="bf-chat-input-bar" style={{ backgroundColor: 'var(--surface)', borderTop: '1px solid var(--border)', padding: '16px 20px', boxShadow: '0 -4px 24px rgba(0,0,0,0.4)', paddingBottom: 'calc(16px + env(safe-area-inset-bottom, 0px))', height: '100%', display: 'flex', flexDirection: 'column' }}>
          {attachedImages.length > 0 && (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', marginBottom: '10px', padding: '10px 12px', backgroundColor: 'var(--surface2)', border: '1px solid var(--border)', borderRadius: '8px' }}>
              <div style={{ width: '100%', fontSize: '11px', color: 'var(--muted)', fontFamily: 'var(--font-mono)', marginBottom: '4px' }}>
                {attachedImages.length} image{attachedImages.length > 1 ? 's' : ''} attached ({MAX_IMAGES} max)
              </div>
              {attachedImages.map((img, i) => (
                <div key={i} style={{ position: 'relative', width: 64, height: 64 }}>
                  <img src={img.dataUrl} alt={img.name} style={{ width: 64, height: 64, objectFit: 'cover', borderRadius: '6px' }} />
                  <button
                    onClick={() => removeImageAt(i)}
                    title="Remove"
                    style={{
                      position: 'absolute', top: -6, right: -6,
                      width: 18, height: 18,
                      background: '#3a1e1e', color: '#c98080',
                      border: '1px solid #6b3030', borderRadius: '50%',
                      cursor: 'pointer', fontSize: '11px',
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      padding: 0, lineHeight: 1,
                    }}
                  >×</button>
                </div>
              ))}
            </div>
          )}
          {/* Markdown formatting toolbar — wraps the selection in markers.
              The composer stays plain markdown text (no rich-text model), so
              typing the syntax by hand works identically to the buttons. */}
          <div style={{ display: 'flex', gap: '6px', marginBottom: '8px', alignItems: 'center', flexShrink: 0 }}>
            {[
              { label: 'B', title: 'Bold  (Cmd/Ctrl-B)', wrap: '**', extra: { fontWeight: 700 } },
              { label: 'I', title: 'Italic  (Cmd/Ctrl-I)', wrap: '*', extra: { fontStyle: 'italic' } },
              { label: '</>', title: 'Inline code  (Cmd/Ctrl-E)', wrap: '`', extra: { fontFamily: 'var(--font-mono)', fontSize: '11px' } },
              { label: '≡', title: 'Bullet list  (prefixes lines with - )', prefix: '- ', extra: { fontSize: '15px' } },
            ].map(b => (
              <button
                key={b.label}
                type="button"
                onClick={() => (b.wrap ? applyMarkdown(b.wrap) : applyLinePrefix(b.prefix))}
                disabled={!selectedModel || isLoading}
                title={b.title}
                style={{
                  minWidth: '30px', height: '26px', padding: '0 7px',
                  background: 'var(--surface2)', border: '1px solid var(--border)',
                  borderRadius: '6px', color: 'var(--muted)', lineHeight: 1,
                  cursor: (!selectedModel || isLoading) ? 'not-allowed' : 'pointer',
                  fontSize: '13px',
                  ...b.extra,
                }}
                onMouseOver={e => { if (selectedModel && !isLoading) e.currentTarget.style.color = 'var(--accent)' }}
                onMouseOut={e => { e.currentTarget.style.color = 'var(--muted)' }}
              >{b.label}</button>
            ))}
            <span style={{ fontSize: '10px', color: 'var(--muted)', marginLeft: '4px', fontFamily: 'var(--font-mono)', letterSpacing: '0.04em' }}>
              markdown
            </span>
            {/* How to make a newline is invisible without a hint. It also
                differs by device: desktop has Shift+Enter, touch has no
                Shift so plain Enter is the newline and Send is the sender. */}
            <span
              title={isTouch
                ? 'Enter starts a new line · tap Send to send'
                : 'Enter sends the message · Shift+Enter starts a new line'}
              style={{ fontSize: '10px', color: 'var(--muted)', marginLeft: 'auto', fontFamily: 'var(--font-mono)', letterSpacing: '0.04em', opacity: 0.75 }}
            >
              {isTouch ? '↵ new line · tap Send' : '⇧↵ newline'}
            </span>
          </div>
          <div style={{ display: 'flex', gap: '12px', alignItems: 'stretch', flex: 1, minHeight: 0 }}>
            <label
              htmlFor="image-upload-input"
              title="Attach image (uses vision-capable model — Claude / GPT-4o)"
              style={{
                padding: '12px 14px',
                backgroundColor: 'var(--surface)',
                border: '1px solid var(--border)',
                borderRadius: '10px',
                cursor: isLoading ? 'not-allowed' : 'pointer',
                color: 'var(--muted)',
                fontSize: '16px',
                userSelect: 'none',
                flexShrink: 0,
                alignSelf: 'flex-end',
                lineHeight: '1',
              }}
            >📎</label>
            <input
              id="image-upload-input"
              type="file"
              accept="image/*"
              multiple
              onChange={handleImageSelect}
              disabled={isLoading}
              style={{ display: 'none' }}
            />
            <textarea
              ref={textareaRef}
              value={inputMessage}
              onChange={e => setInputMessage(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={
                selectedModel
                  ? (attachedImages.length > 0
                      ? `Ask about the image${attachedImages.length > 1 ? 's' : ''}...`
                      : (typeof window !== 'undefined' && window.matchMedia('(max-width: 480px)').matches
                          ? 'Message...'
                          : 'Message... (Enter to send, drop images here)'))
                  : 'Select a model first'
              }
              disabled={!selectedModel || isLoading}
              rows={1}
              // Height is controlled by the vertical resize handle above
              // the input panel. Textarea fills its panel via flex stretch;
              // own resize grip is disabled to avoid fighting the handle.
              style={{
                flex: 1,
                padding: '12px 16px',
                borderRadius: '10px',
                border: '1px solid var(--border)',
                backgroundColor: 'var(--surface)',
                color: 'var(--text)',
                fontSize: '14px',
                resize: 'none',
                fontFamily: 'inherit',
                outline: 'none',
                lineHeight: '1.5',
                minHeight: 0,
              }}
            />
            {isLoading ? (
              // While a response is streaming, the Send button transforms
              // into Stop — the operator can interrupt an overlong generation
              // without waiting for it to finish. Aborts the fetch via the
              // AbortController; partial content already streamed stays in
              // the message (per the catch-block handling).
              <button
                onClick={stopMessage}
                title="Stop the brain mid-response"
                style={{
                  padding: '12px 20px',
                  background: 'var(--surface)',
                  color: '#ff6b6b',
                  border: '1px solid #ff6b6b66',
                  borderRadius: '10px',
                  cursor: 'pointer',
                  fontSize: '14px',
                  fontWeight: '600',
                  transition: 'all 0.15s ease',
                  whiteSpace: 'nowrap',
                  flexShrink: 0,
                  alignSelf: 'flex-end',
                }}
                onMouseOver={e => { e.currentTarget.style.background = '#1a0a0a' }}
                onMouseOut={e => { e.currentTarget.style.background = 'var(--surface)' }}
              >
                ■ Stop
              </button>
            ) : (
              <button
                onClick={sendMessage}
                disabled={!inputMessage.trim() || !selectedModel}
                style={{
                  padding: '12px 20px',
                  background: (!inputMessage.trim() || !selectedModel) ? 'var(--surface)' : 'var(--accent)',
                  color: (!inputMessage.trim() || !selectedModel) ? 'var(--muted)' : 'var(--bg)',
                  border: '1px solid var(--border)',
                  borderRadius: '10px',
                  cursor: (!inputMessage.trim() || !selectedModel) ? 'not-allowed' : 'pointer',
                  fontSize: '14px',
                  fontWeight: '600',
                  transition: 'all 0.15s ease',
                  whiteSpace: 'nowrap',
                  flexShrink: 0,
                  alignSelf: 'flex-end',
                }}
              >
                Send
              </button>
            )}
          </div>
        </div>

        </Panel>
        </PanelGroup>
      </Panel>
      </PanelGroup>

      {/* Proposal modal — Phase B classify-and-propose flow. The brain
          proposes how to store the operator's selected message; the
          operator reviews / edits / accepts / rejects. Every decision
          becomes a labeled feedback row that Phase 3 LoRA training will
          consume. */}
      {proposalOpen && (
        <div style={{
          position: 'fixed', inset: 0,
          backgroundColor: 'rgba(0,0,0,0.7)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          zIndex: 200,
          padding: '20px',
        }}>
          <div style={{
            backgroundColor: 'var(--surface)',
            border: '1px solid var(--border)',
            borderRadius: '14px',
            padding: '24px',
            width: 'min(640px, 100%)',
            maxHeight: '90vh',
            overflowY: 'auto',
            color: 'var(--text)',
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
              <h2 style={{ fontSize: '15px', fontFamily: 'Lora, Georgia, serif', margin: 0 }}>
                Store to brain memory
              </h2>
              <button
                onClick={closeProposalModal}
                disabled={proposalLoading}
                style={{ background: 'transparent', border: 'none', color: 'var(--muted)', cursor: proposalLoading ? 'wait' : 'pointer', fontSize: '18px', lineHeight: 1, padding: 0 }}
                title="Cancel"
              >
                ×
              </button>
            </div>

            {proposalLoading && !proposal ? (
              <div style={{ color: 'var(--muted)', fontSize: '13px', padding: '20px 0' }}>
                Asking the brain to classify…
              </div>
            ) : proposalError ? (
              <div style={{ backgroundColor: '#1a0a0a', border: '1px solid #ff6b6b30', borderRadius: '8px', padding: '12px', color: '#ff6b6b', fontSize: '12px', marginBottom: '12px' }}>
                {proposalError}
              </div>
            ) : draft ? (
              <>
                <div style={{ fontSize: '11px', color: 'var(--muted)', marginBottom: '14px', fontStyle: 'italic' }}>
                  {proposal?.rationale || 'Brain proposes:'}
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '90px 1fr', rowGap: '10px', columnGap: '10px', alignItems: 'center', marginBottom: '14px' }}>
                  <label style={{ fontSize: '11px', color: 'var(--muted)' }}>layer</label>
                  <div>
                    <CustomSelect
                      value={draft.layer}
                      onChange={(v) => setDraft(d => ({ ...d, layer: v }))}
                      title="Storage layer"
                      minWidth={180}
                      options={[
                        { value: 'episodic',   label: 'episodic' },
                        { value: 'semantic',   label: 'semantic' },
                        { value: 'procedural', label: 'procedural' },
                      ]}
                    />
                  </div>

                  <label style={{ fontSize: '11px', color: 'var(--muted)' }}>path</label>
                  <input
                    value={draft.path}
                    onChange={e => setDraft(d => ({ ...d, path: e.target.value }))}
                    placeholder="YYYY-MM-DD_slug.md"
                    style={{ background: 'var(--bg)', border: '1px solid var(--border)', color: 'var(--text)', borderRadius: '6px', padding: '6px 8px', fontFamily: 'DM Mono, monospace', fontSize: '12px' }}
                  />

                  <label style={{ fontSize: '11px', color: 'var(--muted)' }}>title</label>
                  <input
                    value={draft.title}
                    onChange={e => setDraft(d => ({ ...d, title: e.target.value }))}
                    style={{ background: 'var(--bg)', border: '1px solid var(--border)', color: 'var(--text)', borderRadius: '6px', padding: '6px 8px', fontSize: '13px' }}
                  />

                  <label style={{ fontSize: '11px', color: 'var(--muted)' }}>tags</label>
                  <input
                    value={draft.tags}
                    onChange={e => setDraft(d => ({ ...d, tags: e.target.value }))}
                    placeholder="comma, separated"
                    style={{ background: 'var(--bg)', border: '1px solid var(--border)', color: 'var(--text)', borderRadius: '6px', padding: '6px 8px', fontFamily: 'DM Mono, monospace', fontSize: '12px' }}
                  />
                </div>

                <label style={{ fontSize: '11px', color: 'var(--muted)', display: 'block', marginBottom: '4px' }}>content</label>
                <textarea
                  value={draft.content}
                  onChange={e => setDraft(d => ({ ...d, content: e.target.value }))}
                  rows={8}
                  style={{ width: '100%', background: 'var(--bg)', border: '1px solid var(--border)', color: 'var(--text)', borderRadius: '6px', padding: '8px', fontFamily: 'inherit', fontSize: '13px', lineHeight: 1.5, resize: 'vertical', boxSizing: 'border-box' }}
                />

                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '18px', gap: '10px', flexWrap: 'wrap' }}>
                  <button
                    onClick={rejectProposal}
                    disabled={proposalLoading}
                    title="Don't store. Still logs as negative training signal."
                    style={{ background: 'transparent', border: '1px solid #ff6b6b66', color: '#ff6b6b', borderRadius: '8px', padding: '8px 14px', cursor: proposalLoading ? 'wait' : 'pointer', fontSize: '13px' }}
                  >
                    Reject
                  </button>
                  <div style={{ display: 'flex', gap: '8px' }}>
                    <button
                      onClick={closeProposalModal}
                      disabled={proposalLoading}
                      style={{ background: 'transparent', border: '1px solid var(--border)', color: 'var(--muted)', borderRadius: '8px', padding: '8px 14px', cursor: proposalLoading ? 'wait' : 'pointer', fontSize: '13px' }}
                    >
                      Cancel
                    </button>
                    <button
                      onClick={() => commitProposal('accept')}
                      disabled={proposalLoading}
                      title="Save with the proposal as-is (or your edits)"
                      style={{ background: 'var(--accent)', color: 'var(--bg)', border: 'none', borderRadius: '8px', padding: '8px 14px', cursor: proposalLoading ? 'wait' : 'pointer', fontSize: '13px', fontWeight: 600 }}
                    >
                      {proposalLoading ? '…' : 'Accept'}
                    </button>
                  </div>
                </div>
              </>
            ) : null}
          </div>
        </div>
      )}

      {/* New session modal */}
      {showNameModal && (
        <div style={{
          position: 'fixed', inset: 0,
          backgroundColor: 'rgba(0,0,0,0.7)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          zIndex: 200,
        }}>
          <div style={{
            backgroundColor: 'var(--surface)',
            border: '1px solid var(--border)',
            borderRadius: '14px',
            padding: '28px',
            width: '380px',
            maxWidth: '90vw',
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
              <h2 style={{ margin: 0, fontSize: '16px', fontWeight: '600', color: 'var(--text)' }}>New session</h2>
              <button onClick={() => setShowNameModal(false)} style={{ background: 'none', border: 'none', color: 'var(--muted)', fontSize: '20px', cursor: 'pointer' }}>×</button>
            </div>
            <form onSubmit={async e => {
              e.preventDefault()
              const title = newChatName.trim() || 'New Chat'
              setShowNameModal(false)
              await createNewSession(title)
            }}>
              <input
                type="text"
                value={newChatName}
                onChange={e => setNewChatName(e.target.value)}
                placeholder="Session name (optional)"
                autoFocus
                style={{
                  width: '100%',
                  padding: '10px 14px',
                  backgroundColor: 'var(--surface)',
                  border: '1px solid var(--border)',
                  borderRadius: '8px',
                  color: 'var(--text)',
                  fontSize: '14px',
                  outline: 'none',
                  boxSizing: 'border-box',
                  marginBottom: '16px',
                }}
              />
              <div style={{ display: 'flex', gap: '10px', justifyContent: 'flex-end' }}>
                <button type="button" onClick={() => setShowNameModal(false)} style={{ padding: '8px 16px', backgroundColor: 'transparent', border: '1px solid var(--border)', borderRadius: '8px', color: 'var(--muted)', cursor: 'pointer', fontSize: '14px' }}>
                  Cancel
                </button>
                <button type="submit" style={{ padding: '8px 16px', background: 'var(--accent)', border: 'none', borderRadius: '8px', color: 'var(--bg)', cursor: 'pointer', fontSize: '14px', fontWeight: '600' }}>
                  Create
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Name-your-brain modal — runs persona personalization (the step the
          provisioner does by hand) from the console. */}
      {showPersonalize && (
        <div style={{
          position: 'fixed', inset: 0,
          backgroundColor: 'rgba(0,0,0,0.7)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          zIndex: 200,
        }}>
          <div style={{
            backgroundColor: 'var(--surface)',
            border: '1px solid var(--border)',
            borderRadius: '14px',
            padding: '28px',
            width: '420px',
            maxWidth: '90vw',
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
              <h2 style={{ margin: 0, fontSize: '16px', fontWeight: '600', color: 'var(--text)' }}>Name your brain</h2>
              <button onClick={() => setShowPersonalize(false)} style={{ background: 'none', border: 'none', color: 'var(--muted)', fontSize: '20px', cursor: 'pointer' }}>×</button>
            </div>
            <p style={{ fontSize: '12px', color: 'var(--muted)', lineHeight: 1.6, margin: '0 0 18px' }}>
              This fills the brain's persona document, strips the template banner, and reloads it as a named brain. You can keep editing the persona afterwards.
            </p>
            <form onSubmit={e => { e.preventDefault(); personalizeBrain() }}>
              <label style={{ display: 'block', fontSize: '11px', color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: '5px' }}>
                Brain name
              </label>
              <input
                type="text"
                value={personaBrainName}
                onChange={e => setPersonaBrainName(e.target.value)}
                placeholder="what you'll call it — e.g. Hbar"
                autoFocus
                maxLength={80}
                style={{
                  width: '100%', padding: '10px 14px',
                  backgroundColor: 'var(--surface)', border: '1px solid var(--border)',
                  borderRadius: '8px', color: 'var(--text)', fontSize: '14px',
                  outline: 'none', boxSizing: 'border-box', marginBottom: '14px',
                  fontFamily: 'inherit',
                }}
              />
              <label style={{ display: 'block', fontSize: '11px', color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: '5px' }}>
                Owner name
              </label>
              <input
                type="text"
                value={personaOwnerName}
                onChange={e => setPersonaOwnerName(e.target.value)}
                placeholder="who it belongs to — e.g. Yury"
                maxLength={80}
                style={{
                  width: '100%', padding: '10px 14px',
                  backgroundColor: 'var(--surface)', border: '1px solid var(--border)',
                  borderRadius: '8px', color: 'var(--text)', fontSize: '14px',
                  outline: 'none', boxSizing: 'border-box', marginBottom: '14px',
                  fontFamily: 'inherit',
                }}
              />
              {personaError && (
                <div style={{
                  backgroundColor: '#3a1e1e', color: '#c98080',
                  fontSize: '12px', padding: '8px 12px', borderRadius: '8px',
                  marginBottom: '14px', fontFamily: 'var(--font-mono)',
                }}>
                  {personaError}
                </div>
              )}
              <div style={{ display: 'flex', gap: '10px', justifyContent: 'flex-end' }}>
                <button type="button" onClick={() => setShowPersonalize(false)} style={{ padding: '8px 16px', backgroundColor: 'transparent', border: '1px solid var(--border)', borderRadius: '8px', color: 'var(--muted)', cursor: 'pointer', fontSize: '14px' }}>
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={personalizing || !personaBrainName.trim() || !personaOwnerName.trim()}
                  style={{
                    padding: '8px 16px',
                    background: (personalizing || !personaBrainName.trim() || !personaOwnerName.trim()) ? 'var(--surface2)' : 'var(--accent)',
                    border: 'none', borderRadius: '8px',
                    color: (personalizing || !personaBrainName.trim() || !personaOwnerName.trim()) ? 'var(--muted)' : 'var(--bg)',
                    cursor: (personalizing || !personaBrainName.trim() || !personaOwnerName.trim()) ? 'not-allowed' : 'pointer',
                    fontSize: '14px', fontWeight: '600',
                  }}
                >
                  {personalizing ? 'Naming...' : 'Name brain'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </>
  )
}
