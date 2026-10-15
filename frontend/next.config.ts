import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactCompiler: true,
  distDir: process.env.NEXT_DIST_DIR ?? ".next",
  // Docker 部署: 生成自包含的最小运行时目录
  output: "standalone",
  // 本机 Docker 的 WSL 内存只有 4GB，构建期多进程会 OOM：限制并发并关掉 worker 线程
  experimental: {
    cpus: 1,
    workerThreads: false,
  },
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
