import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactCompiler: true,
  distDir: process.env.NEXT_DIST_DIR ?? ".next",
  // Docker 部署: 生成自包含的最小运行时目录
  output: "standalone",
  // 开发环境 API 代理：/api/* 转发到 FastAPI（生产由 nginx 分流，不经 Next.js）
  async rewrites() {
    const target = process.env.API_PROXY_TARGET ?? "http://localhost:8001";
    return [
      {
        source: "/api/:path*",
        destination: `${target}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
