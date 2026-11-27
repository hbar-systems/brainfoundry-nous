// Whether the spiders walk (MEMBER-SCREEN-2, 2026-11-27): only when the owner turned them on with the chip on
// /cortex, which stores localStorage "bf-spiders" = "1". Missing, "0" or anything else is off, on every brain.
// Before this a missing value meant on, so every new browser (a member's first screen) had spiders.
const spidersFrom = (v) => v === '1'

module.exports = { spidersFrom }
