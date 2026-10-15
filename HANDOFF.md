# One-Tick 维护交接

> 更新时间：2026-10-15
> 面向对象：项目维护者、后续接手开发者、代码审阅者
> 说明：这是当前仓库的维护说明，不包含服务器账号、密钥、内网地址或本地环境路径。

---

## 1. 项目定位

One-Tick 一刻是一个学习闭环平台：计划、任务、专注、打卡、植物农场、3D 小岛、统计和 AI 助手共享同一套数据。

AI 能力分为四层：

- RAG 个人知识库
- 长期记忆
- Agent Runtime 和审批
- 多模型分档与降级

架构和 AI 请求链路见：

- [`README.md`](README.md)
- [`docs/architecture.md`](docs/architecture.md)
- [`docs/ai-engineering.md`](docs/ai-engineering.md)

---

## 2. 运行时拓扑

```text
Nginx :80
├── /health, /api/*, /ws → FastAPI :8001
└── /                     → Next.js :3000

FastAPI → PostgreSQL 16 + pgvector
Next.js → 服务端 fetch FastAPI（容器网络内）
```

开发环境：

- Next.js 的 `/api/*` rewrite 指向 `API_PROXY_TARGET`。
- 生产环境由 Nginx 完成页面、REST 和 WebSocket 分流。

---

## 3. 目录职责

| 目录 | 职责 |
|---|---|
| `app/main.py` | FastAPI 入口，挂载 REST 和 WebSocket |
| `app/routers/` | 认证、学习业务、AI、Agent、知识库等协议入口 |
| `app/services/` | 统计、计划拆分、通知、用量、OSS 和用户初始化 |
| `app/ai/` | 模型池、RAG、记忆、Agent Runtime 和工具 |
| `app/models/` | SQLAlchemy ORM |
| `alembic/versions/` | `0001 → 0002 → 0003 → 0004` 迁移链 |
| `frontend/src/` | Next.js 页面、组件和 Server Actions |
| `specs/` | 功能规格、技术计划和任务状态 |
| `docs/` | 架构、ADR、开发、测试和 AI 工程说明 |
| `tests/` | 不依赖外部服务的单元测试 |
| `scripts/rag_eval/` | RAG 评测和指标记录 |

---

## 4. 本地启动

```bash
cp .env.example .env
docker compose up -d db
python -m venv .venv
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8001
```

前端：

```bash
cd frontend
npm install
API_PROXY_TARGET=http://localhost:8001 npm run dev
```

环境变量要求：

- `JWT_SECRET` 必须替换默认值。
- `POSTGRES_PASSWORD` 使用本地或部署环境自己的值。
- AI 功能至少配置一个对话 provider；知识库向量需要 embedding key。
- 不提交 `.env`、API Key、OSS Secret 或服务器凭据。

---

## 5. 部署检查清单

部署前：

- [ ] `.env`、密钥和本地数据未进入打包内容。
- [ ] 前端已执行 `npm run typecheck`、`npm run lint`、`npm run build`。
- [ ] 后端已执行 `python -m compileall -q app` 和单元测试。
- [ ] 检查数据库备份和回滚方案。

部署后：

- [ ] `docker compose ps` 显示 db、app、web、nginx 状态正常。
- [ ] `docker compose logs --tail=100 app` 中没有迁移或启动错误。
- [ ] `/health` 返回 `{"status":"ok"}`。
- [ ] 登录、打卡、专注、花园、AI 会话和知识库问答各做一次 smoke test。
- [ ] 确认 `alembic current` 与代码预期版本一致。

后端容器启动时会自动执行：

```bash
alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8001
```

---

## 6. 关键运行约束

### 数据库

- 业务数据和 pgvector 向量共用 PostgreSQL。
- `DocumentChunk.embedding` 为 1024 维向量。
- HNSW 索引由 `0004_rag_vector_index` 创建。
- 手工修改过 schema 后，不要只依赖 Alembic 版本号，必须检查实际索引是否存在。

### AI 请求

- `/api/ai` 在线程中执行阻塞式模型调用，通过队列向 `StreamingResponse` 推送增量。
- 流式线程必须使用独立数据库 Session，不能复用请求线程注入的 Session。
- 工具必须通过 `create_*_tools(user_id)` 创建，不能绕过用户隔离。
- 模型池状态位于进程内，多实例部署前需要外置状态。

### WebSocket

- 连接集合位于进程内，当前只支持单实例。
- 已有心跳、限流和 `clientId` 去重，但不能替代分布式消息层。
- 聊天室 AI 当前是一次生成后分段广播，不是原生 token 流。

---

## 7. 常见故障排查

| 现象 | 优先检查 |
|---|---|
| 后端启动时报配置校验错误 | `.env` 是否包含非法字段；应用已设置为忽略 Compose 专用变量 |
| 前端 502 / API 不可达 | 容器网络、`API_INTERNAL_URL`、Nginx upstream |
| AI 首字节延迟很长 | 工具循环轮数、provider 限流、模型池降级日志 |
| AI 回复为空 | provider 配额、流式异常、服务端日志 |
| 知识库问答答非所问 | chunk 数量、embedding 是否成功、`ef_search`、召回来源 |
| 小岛树数量不动 | StudyRecord 是否落库、Garden 能量、浇水是否超过最高阶段 |
| WebSocket 连接失败 | Cookie / token、Nginx Upgrade 头、心跳超时 |
| 前端构建 OOM | WSL / Docker 内存、Next.js 构建并发配置 |

---

## 8. 已知风险

1. WebSocket 和模型池状态不跨进程。
2. 签到和专注幂等主要依赖应用层先查后写。
3. RAG 生产查询仍取回整行 DocumentChunk，包括不使用的 embedding 字段。
4. 端到端评测样本较小，结果主要用于行为验证。
5. 当前没有统一异常追踪、告警和自动备份。
6. 前端 lint 仍有历史 warning，尚未全部清零。

---

## 9. 下一步

- [ ] 将 WebSocket 广播和模型可用性状态迁移到共享存储。
- [ ] 为签到和专注增加数据库唯一约束。
- [ ] 对 RAG 查询做列裁剪，并重新跑检索评测。
- [ ] 增加数据库集成测试和 provider stub 测试。
- [ ] 增加告警、备份和恢复演练。
- [ ] 为部署增加 Release 版本号和回滚说明。