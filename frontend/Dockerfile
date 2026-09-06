# ============================================================
# 前端（Next.js 纯 UI 层）构建镜像
# 数据/业务全部由 FastAPI 后端提供（同域反代 / api 内部直连），
# 本镜像只负责页面渲染，不含数据库与业务逻辑。
# 基础镜像用 bookworm-slim（本机构建环境已有缓存，避免 Docker Hub 拉取 alpine 过慢）
# ============================================================

# ---- Stage 1: Build ----
FROM node:22-bookworm-slim AS builder
WORKDIR /app

# 国内镜像加速
RUN npm config set registry https://registry.npmmirror.com

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
ENV NEXT_TELEMETRY_DISABLED=1
# 构建（output: "standalone"）
RUN npm run build

# ---- Stage 2: Production ----
FROM node:22-bookworm-slim AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV HOSTNAME=0.0.0.0
ENV PORT=3000

# 创建非 root 用户
RUN groupadd --system --gid 1001 nodejs && \
    useradd --system --uid 1001 --gid nodejs nextjs

# 从 builder 复制 standalone 输出
COPY --from=builder /app/.next/standalone ./

# 复制静态资源（standalone 不自动包含）
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public

RUN chown -R nextjs:nodejs /app

USER nextjs

EXPOSE 3000

CMD ["node", "server.js"]
