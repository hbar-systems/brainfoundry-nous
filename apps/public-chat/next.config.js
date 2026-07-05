/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  // Pin the standalone file-tracing root to this app dir so `server.js` always
  // lands at `.next/standalone/server.js` (what the Dockerfile CMD expects),
  // regardless of any ambient lockfiles higher up the tree. In Next 15 this key
  // moved out of `experimental` to the top level.
  outputFileTracingRoot: __dirname,
}

module.exports = nextConfig
