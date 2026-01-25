import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // basePath and assetPrefix are set dynamically during deployment
  // For local development, these are empty (default)
  // For production deployment to /test, these are set to '/test' by deploy.sh
  basePath: process.env.NEXT_PUBLIC_BASE_PATH || '',
  assetPrefix: process.env.NEXT_PUBLIC_BASE_PATH || '',
};

export default nextConfig;
