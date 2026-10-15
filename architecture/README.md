# Architecture

该目录保存 One-Tick 的运行时架构源文件和可浏览产物。

| 文件 | 说明 |
|---|---|
| `one-tick.architecture.json` | Archify 架构源文件，包含组件、边界、连接和视图 |
| `one-tick.architecture.html` | 可独立打开的交互式架构图 |
| `one-tick.architecture.png` | 用于 README 或 GitHub 预览的静态图 |

图中覆盖：

- Nginx 同域入口
- Next.js 前端
- FastAPI 业务与 AI 编排
- WebSocket 聊天室
- PostgreSQL + pgvector
- 外部模型服务与 OSS

维护规则：

1. 架构发生变化时先修改 JSON。
2. 重新生成 HTML 和预览图。
3. 不要把凭据、真实服务器地址或本地路径写入图中。