import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  // Same-origin API proxy for production (Vercel -> Render). Only /api/* is forwarded, and only when BACKEND_URL is set.
  async rewrites() {
    const backend = process.env.BACKEND_URL?.trim().replace(/\/+$/, "");
    if (!backend) return [];
    if (!/^https?:\/\//.test(backend)) throw new Error("BACKEND_URL must start with http:// or https://");
    return [{ source: "/api/:path*", destination: `${backend}/api/:path*` }];
  },
  // Basic hardening headers. A Content-Security-Policy needs nonce setup for Next's inline scripts and is listed as future work.
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          { key: "X-Frame-Options", value: "DENY" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
        ],
      },
    ];
  },
};

export default nextConfig;
