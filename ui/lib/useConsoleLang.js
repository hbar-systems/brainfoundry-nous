// The console's language for a page outside the chat (2026-11-15): the bridge's layout.json key lang,
// read once from GET /cc/layout; English when unset or when the bridge does not answer.
import { useEffect, useState } from 'react'

export default function useConsoleLang() {
  const [lang, setLang] = useState('en')
  useEffect(() => {
    let on = true
    fetch('/cc/layout', { cache: 'no-store' }).then(r => (r.ok ? r.json() : null)).then(d => { if (on && d && d.lang) setLang(d.lang) }).catch(() => {})
    return () => { on = false }
  }, [])
  return lang
}
