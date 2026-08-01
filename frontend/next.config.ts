import type { NextConfig } from "next";

const backendUrl = process.env.BACKEND_URL;

const nextConfig: NextConfig = {
  async rewrites() {
    if (!backendUrl) return [];
    const proxy = (prefix: string) => ({
      source: `/${prefix}/:path*`,
      destination: `${backendUrl}/${prefix}/:path*`,
    });
    return [
      proxy("tasks"),
      proxy("baseline"),
      proxy("session"),
      proxy("participants"),
      proxy("hints"),
      { source: "/health", destination: `${backendUrl}/health` },
    ];
  },
};

export default nextConfig;
