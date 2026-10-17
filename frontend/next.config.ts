import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Self-contained server for the container image (frontend/Dockerfile).
  output: "standalone",
  // Tests are type-checked by `pnpm typecheck`; the build skips them (contract.test.ts reads
  // a backend file that is not in the frontend image).
  typescript: { tsconfigPath: "tsconfig.build.json" },
};

export default nextConfig;
