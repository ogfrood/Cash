import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // better-sqlite3 is a native addon: it must stay external to the server
  // bundle, otherwise Turbopack tries to bundle the .node binary and fails.
  serverExternalPackages: ["better-sqlite3"],
  // Hide the little "N" dev-mode badge that Next.js floats over the page —
  // it lands in every screenshot otherwise.
  devIndicators: false,
};

export default nextConfig;
