import type { NextConfig } from "next";
import { apiBase, assertProductionApi } from "./lib/api/config";

const API = apiBase();
assertProductionApi(API);

const nextConfig: NextConfig = {
  poweredByHeader: false,
  images: {
    remotePatterns: [],
  },
  async rewrites() {
    return [{ source: "/v1/:path*", destination: `${API}/v1/:path*` }];
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
        ],
      },
    ];
  },
};

export default nextConfig;
