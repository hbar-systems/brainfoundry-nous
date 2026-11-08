// The welcome film's version (ui/public/onboarding/index.html, "version" in its
// config block). Raise both together, only when the film really changes: every
// fresh brain whose owner saw a lower version is shown it again. 2026-10-23.
export const WELCOME_VERSION = 1

// Where "Talk to it" lands (2026-11-08): the thread (/talk, the console's talk view) when CC is on
// (apps/list ccHome), Chat only on a brain without CC. Unknown (the list did not answer): the thread.
export const landing = (apps) => (apps && apps.ccHome === false ? '/chat' : '/talk')
