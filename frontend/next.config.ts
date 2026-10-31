import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Keep `next dev` output apart from `next build` output so running a build
  // while the dev server is up does not break the dev server (Next 15 shares .next otherwise).
  distDir: process.env.NODE_ENV === "development" ? ".next-dev" : ".next",
  output: "export",
  trailingSlash: false,
  images: { unoptimized: true },
  reactStrictMode: true,
};

export default nextConfig;
