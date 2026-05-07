import { useEffect, useRef, useState } from 'react'

// Flat custom dropdown — replaces native <select> across the chat header.
// Theme-aware via var(--*). Closes on outside click and Escape. Each option
// can carry a `style` prop for per-option styling (used by the font picker
// to preview each font in its own typeface, and by the theme picker to show
// a swatch in each row's accent color).
export default function CustomSelect({
  value,
  onChange,
  options,
  title,
  minWidth = 110,
  align = 'left',
}) {
  const [open, setOpen] = useState(false)
  const ref = useRef(null)

  useEffect(() => {
    if (!open) return
    const onDocClick = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false)
    }
    const onKey = (e) => {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onDocClick)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDocClick)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  const current = options.find(o => o.value === value)

  return (
    <div ref={ref} style={{ position: 'relative', minWidth }}>
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        title={title}
        style={{
          width: '100%',
          padding: '7px 10px 7px 12px',
          borderRadius: '8px',
          border: '1px solid var(--border)',
          backgroundColor: 'var(--surface)',
          color: 'var(--text)',
          fontSize: '12px',
          fontFamily: 'var(--font-mono)',
          letterSpacing: '0.02em',
          cursor: 'pointer',
          outline: 'none',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: '8px',
          transition: 'border-color 0.12s ease, background-color 0.12s ease',
        }}
        onMouseOver={e => { e.currentTarget.style.borderColor = 'var(--accent)' }}
        onMouseOut={e => { e.currentTarget.style.borderColor = 'var(--border)' }}
        aria-haspopup="listbox"
        aria-expanded={open}
      >
        <span style={{
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
          flex: 1,
          textAlign: 'left',
          ...(current?.triggerStyle || {}),
        }}>
          {current?.label || value || '—'}
        </span>
        <span style={{
          fontSize: '9px',
          color: 'var(--muted)',
          transform: open ? 'rotate(180deg)' : 'rotate(0deg)',
          transition: 'transform 0.15s ease',
          display: 'inline-block',
          lineHeight: 1,
        }}>▾</span>
      </button>

      {open && (
        <div
          role="listbox"
          style={{
            position: 'absolute',
            top: 'calc(100% + 4px)',
            [align]: 0,
            minWidth: '100%',
            background: 'var(--surface)',
            border: '1px solid var(--border)',
            borderRadius: '10px',
            padding: '4px',
            boxShadow: '0 8px 24px rgba(0,0,0,0.35)',
            zIndex: 200,
            maxHeight: '320px',
            overflowY: 'auto',
          }}
        >
          {options.map(o => {
            const selected = o.value === value
            return (
              <div
                key={o.value}
                role="option"
                aria-selected={selected}
                onClick={() => { onChange(o.value); setOpen(false) }}
                style={{
                  padding: '7px 10px',
                  borderRadius: '6px',
                  cursor: 'pointer',
                  fontSize: '12px',
                  color: selected ? 'var(--text)' : 'var(--text)',
                  backgroundColor: selected ? 'var(--surface2)' : 'transparent',
                  fontFamily: 'var(--font-mono)',
                  letterSpacing: '0.02em',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  transition: 'background-color 0.1s ease',
                  ...(o.optionStyle || {}),
                }}
                onMouseOver={e => { if (!selected) e.currentTarget.style.backgroundColor = 'var(--surface2)' }}
                onMouseOut={e => { if (!selected) e.currentTarget.style.backgroundColor = 'transparent' }}
              >
                {o.swatch && (
                  <span style={{
                    width: '10px',
                    height: '10px',
                    borderRadius: '50%',
                    background: o.swatch,
                    border: '1px solid var(--border)',
                    flexShrink: 0,
                  }} />
                )}
                <span style={{ flex: 1, textAlign: 'left' }}>{o.label}</span>
                {selected && (
                  <span style={{ fontSize: '11px', color: 'var(--accent)', lineHeight: 1 }}>●</span>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
