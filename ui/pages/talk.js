// The CC page at a second address (2026-10-06). Caddy sends /cc and /cc/* to the bridge, so a
// fresh load of /cc (an iframe on /panes, a link opened in a new tab) reached the bridge and
// showed {"error": "not_found"}; the CC tab only worked through in-page navigation. /talk is
// served by the console like every other page.
export { default } from './cc'
