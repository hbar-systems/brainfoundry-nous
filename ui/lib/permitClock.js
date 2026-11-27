// A card's clock (PERMIT-SAY-1, 2026-11-27, hbar: "That Allow did not reach the job: could not approve:
// PermitError - again issue!"). A card is a permit that lives 15 minutes; after that the bridge has told the
// job no and a press can only fail. The card shows the minutes it has left and turns visibly "expired" at
// zero, so a dead card is not pressed. Pure functions, no DOM: ui/pages/cc.js uses them,
// tests/test_cc_box.py runs them under node.
//
// expiresAt: the bridge's epoch seconds (card.expires_at). Missing (an older card): the clock starts when
// the page first saw the card (seenMs) and runs ttlSeconds from there. No ttl either: no clock.

function cardClock(expiresAt, ttlSeconds, nowMs, seenMs) {
  let end = Number(expiresAt) > 0 ? Number(expiresAt) * 1000 : 0
  if (!end && Number(ttlSeconds) > 0 && Number(seenMs) > 0) end = Number(seenMs) + Number(ttlSeconds) * 1000
  if (!end) return { known: false, expired: false, left: null, label: '' }
  const left = Math.max(0, Math.round((end - Number(nowMs)) / 1000))
  if (left <= 0) return { known: true, expired: true, left: 0, label: 'expired' }
  const mins = Math.ceil(left / 60)
  return { known: true, expired: false, left, label: left < 60 ? 'under a minute left' : `${mins} min left` }
}

// What the page says after a press, from the bridge's answer. ok + "already allowed" is fine, not an error.
function pressWords(data, action) {
  const d = data || {}
  if (d.ok && d.status === 'already allowed') return { error: false, text: 'Already allowed; nothing more to do.' }
  if (d.ok) return { error: false, text: '' }
  const verb = action === 'approve' ? 'Allow' : 'Refuse'
  return { error: true, text: `That ${verb} did nothing: ${d.error || 'the bridge did not say why'}.` }
}

module.exports = { cardClock, pressWords }
