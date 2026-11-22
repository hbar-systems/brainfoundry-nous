/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  // Pin the standalone file-tracing root to this app dir so `server.js` lands at
  // `.next/standalone/server.js` (what the Dockerfile CMD expects). In Next 15 this
  // key moved out of `experimental` to the top level.
  outputFileTracingRoot: __dirname,
}

module.exports = nextConfig
