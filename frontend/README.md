# One-Tick Web

One-Tick 的 Next.js 前端。该服务只负责页面渲染、交互和 Service Action，业务数据全部来自 `app/` 下的 FastAPI 服务。

## 本地开发

```bash
npm install
API_PROXY_TARGET=http://localhost:8001 npm run dev
```

浏览器访问 `http://localhost:3000`。

## 生产构建

```bash
npm run typecheck
npm run lint
npm run build
```

生产环境由 Nginx 将 `/api/*` 和 `/ws` 转发到 FastAPI，其余请求转发到 Next.js。前端不应直接访问数据库或模型供应商。

## 目录

```text
src/app/          App Router 页面和 Server Actions
src/components/   UI、学习工作区、Agent、知识库等组件
src/lib/          客户端工具、API 客户端、Markdown 工具
src/context/      场景、主题等跨页面上下文
public/           静态资源
```

更多项目信息见仓库根目录 [`../README.md`](../README.md)。
