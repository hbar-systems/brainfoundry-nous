"""
api/onboarding/ — first-run "become-you" onboarding for a fresh brain.

A cold owner lands on a brand-new (empty-corpus) brain and, within ~2 minutes
and without uploading anything or pasting an API key, gets a mind that speaks
first, reflects them back sharply, and visibly forms a model of them in a side
panel — all stored only in their own brain.

Three pieces:
  - core.py           — auth-agnostic logic: fresh-brain detection, the
                        distinct first-run persona, the opener, and the
                        per-turn fact extraction. Reasoner is INJECTED so this
                        module never imports a key.
  - trial_reasoner.py — an operator-funded, cost/rate-capped SHARED reasoner so
                        a keyless fresh brain can still reason sharply. A
                        dedicated key (TRIAL_REASONER_API_KEY), kept entirely
                        separate from the brain's own provider clients, with
                        hard per-session / per-IP / brain-wide caps, fail-closed.

The whole surface is INERT unless a brain is genuinely fresh AND (for the
trial path) a trial key is configured — so this template change is a no-op for
every already-provisioned brain. See core.is_fresh_brain() and
trial_reasoner.is_available().
"""
