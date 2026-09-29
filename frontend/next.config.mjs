/** @type {import('next').NextConfig} */

// The browser only ever talks to the website; the website forwards /api/* to the backend.
// This lets one public link (e.g. a Cloudflare tunnel) serve both, and avoids CORS.
const BACKEND_URL = process.env.BACKEND_URL || 'http://127.0.0.1:8000';

const nextConfig = {
  async rewrites() {
    return [
      { source: '/api/:path*', destination: `${BACKEND_URL}/api/:path*` },
      { source: '/health', destination: `${BACKEND_URL}/health` },
    ];
  },
  experimental: {
    // Voyage planning can take ~25 s on the first request; the default proxy timeout is 30 s.
    proxyTimeout: 120000,
  },
};

export default nextConfig;
