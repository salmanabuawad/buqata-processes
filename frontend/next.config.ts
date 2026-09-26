import type { NextConfig } from "next";
import { PHASE_DEVELOPMENT_SERVER } from "next/constants";

// Production is a static export served by nginx, which also proxies /api to
// FastAPI. The dev server does the proxying itself (rewrites are dev-only,
// because static exports cannot contain them).
export default function config(phase: string): NextConfig {
  if (phase === PHASE_DEVELOPMENT_SERVER) {
    const api = process.env.API_ORIGIN ?? "http://127.0.0.1:8000";
    return {
      async rewrites() {
        return [{ source: "/api/:path*", destination: `${api}/api/:path*` }];
      },
    };
  }
  return {
    output: "export",
    trailingSlash: true,
    images: { unoptimized: true },
  };
}
