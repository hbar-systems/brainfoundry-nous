// The console's home (NAV-1, hbar 2026-11-13: "nobody knows that to press brain or hbar ... will give
// you the thread page that should be main page. it has always been going to /chat").
// On a brain with CC the home is the conversation page with its threads: "/" (the same page as /talk),
// opened with the thread list showing (?threads=1). The brand (symbol and name) goes there, and so does
// the menu entry "Chat"; /chat stays a working address for the old page of many chats.
// Without CC nothing changes: the brand goes to the dashboard at "/", Chat to /chat.
export const HOME_THREADS = '/?threads=1'

// tabs: [{ id, href, label }] as the Nav holds them (from /apps/list, or the fallback).
export const ccHomeOf = (tabs) => (tabs || []).some(t => t && t.id === '_cc' && t.href === '/')

export const homeHref = (tabs) => (ccHomeOf(tabs) ? HOME_THREADS : '/')

// Where a menu entry points: on a CC brain, Chat is the home, not the old /chat page.
export const menuHref = (tab, tabs) => (tab && tab.id === '_chat' && ccHomeOf(tabs) ? HOME_THREADS : tab.href)

// The page asks to open its thread list when the address says ?threads=1 (or threads=open).
export const wantsThreads = (search) => {
  try { const v = new URLSearchParams(search || '').get('threads'); return v === '1' || v === 'open' } catch { return false }
}
