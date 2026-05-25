// Default-model resolution for the chat dropdown and the dashboard's
// "Active Model" stat card. Three-layer fallback (in order):
//
//   1. operator's last-selected model — /settings/model { active }
//   2. brain's declared model — /identity { model }
//   3. models[0] — last resort
//
// Each layer is gated on the candidate actually appearing in the available
// models list. A stale settings_store entry referring to a model the brain
// no longer has access to (e.g. BYOK key revoked) falls through to the next
// layer instead of leaving the dropdown stuck on something unselectable.
//
// History: a 2026-05-03 hot-fix hardcoded a "claude" substring match here,
// which silently rotted when the model lineup changed during the 2026-05-21
// GPU benchmark session. This module replaces that pattern with explicit
// signals from settings_store and /identity so adding/removing a model never
// requires a code edit.

export function pickDefaultModel(models, settingsActive, identityModel) {
  if (!Array.isArray(models) || models.length === 0) return ''
  const names = models.map(m => m && m.name).filter(Boolean)
  if (settingsActive && names.includes(settingsActive)) return settingsActive
  if (identityModel && names.includes(identityModel)) return identityModel
  return names[0] || ''
}

// Fetch /api/bf/models + /api/bf/settings/model + /api/bf/identity in parallel
// and return { models, default }. Each fetch is fail-soft: a single failure
// just drops that layer from the fallback chain.
export async function loadModelsAndDefault() {
  const get = (u) => fetch(u).then(r => r.ok ? r.json() : null).catch(() => null)
  const [modelsRes, settingsRes, identityRes] = await Promise.all([
    get('/api/bf/models'),
    get('/api/bf/settings/model'),
    get('/api/bf/identity'),
  ])
  const models = (modelsRes && modelsRes.models) || []
  const settingsActive = settingsRes && settingsRes.active
  const identityModel = identityRes && identityRes.model
  return { models, default: pickDefaultModel(models, settingsActive, identityModel) }
}

// Persist the operator's dropdown choice so refresh / new tab / new chat
// honors it. Fail-soft: a 4xx/5xx doesn't break the UI — the current
// session's selection still works, it just won't survive reload.
export async function persistModelChoice(modelName) {
  if (!modelName) return
  try {
    await fetch('/api/bf/settings/model', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model: modelName }),
    })
  } catch {
    // intentionally silent — caller already updated local state
  }
}
