import Head from 'next/head'
import { useRouter } from 'next/router'
import React, { useEffect, useRef, useState } from 'react'
import { TAPE_CSS, mountTape } from '../lib/tape/tape'

// The memo tape as a console page (TAPE-2, 2026-11-14): the memos, their bits, sign-off and the board, and the
// big record button (talk through: a slice uploaded every 10 s through the console's own /cc/upload, the slice
// list kept in the tape's inbox, the watcher stitches and cuts). Everything it reads or writes goes through
// /cc/tape (scripts/cc/cc_tape.py), which reaches only the tape folder; the console's login guards it like
// every page route. A brain without a tape shows one quiet line and nothing else. ?demo=1 draws sample memos.

export default function TapePage() {
  const router = useRouter()
  const rootRef = useRef(null)
  const [st, setSt] = useState(null)   // null loading, {tape:false}, {tape:true, dir, vocab, signer}, {error}
  const demo = router.isReady && router.query.demo === '1'

  useEffect(() => {
    if (!router.isReady) return
    if (demo) { setSt({ tape: true, demo: true }); return }
    let live = true
    fetch('/cc/tape', { credentials: 'same-origin', cache: 'no-store' })
      .then(r => (r.ok ? r.json() : Promise.reject(new Error('http ' + r.status))))
      .then(d => { if (live) setSt(d && typeof d === 'object' ? d : { tape: false }) })
      .catch(e => { if (live) setSt({ error: e.message }) })
    return () => { live = false }
  }, [router.isReady, demo])

  useEffect(() => {
    if (!st || !st.tape || !rootRef.current) return
    return mountTape(rootRef.current, { dir: st.dir, vocab: !!st.vocab, signer: st.signer, demo: !!st.demo, world: st.world || '', expose: true })
  }, [st])

  return (
    <>
      <Head><title>tape</title></Head>
      <style dangerouslySetInnerHTML={{ __html: TAPE_CSS + QUIET }} />
      {st && st.tape ? <div className="tp" ref={rootRef} /> : null}
      {st && !st.tape ? (
        <div className="tp-none">{st.error ? 'The tape did not answer (' + st.error + ').' : 'There is no memo tape on this brain.'}</div>
      ) : null}
    </>
  )
}

const QUIET = `
.tp-none{padding:48px 32px;color:var(--muted);font:400 16px/1.5 var(--font-body, system-ui, sans-serif)}
`
