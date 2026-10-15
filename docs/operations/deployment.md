# Deployment and Local Development

## 环境要求

- Python 3.12+
- Node.js 22+
- Docker Desktop 或 Docker Engine + Compose
- PostgreSQL 16 + pgvector

## 本地环境

```bash
cp .env.example .env
```

至少需要配置：

- `JWT_SECRET`
- `POSTGRES_PASSWORD`
- 一个对话 provider：`ALIYUN_API_KEY` 或 `AGNES_API_KEY`
- embedding 使用独立 key 时配置 `EMBEDDING_API_KEY`

不要提交 `.env`。

## 本地后端

```bash
python -m venv .venv
pip install -r requirements.txt
docker compose up -d db
alembic upgrade head
uvicorn app.main:app --reload --port 8001
```

健康检查：

```bash
curl http://localhost:8001/health
```

## 本地前端

```bash
cd frontend
npm install
API_PROXY_TARGET=http://localhost:8001 npm run dev
```

生产构建：

```bash
cd frontend
npm run typecheck
npm run lint
npm run build
```

## Docker Compose

```bash
docker compose up -d --build
docker compose ps
docker compose logs --tail=100 app
```

拓扑：

```text
nginx :80
├── /health, /api/*, /ws → app :8001
└── /                     → web :3000
                              │
app → PostgreSQL 16 + pgvector
```

容器启动时执行：

```bash
alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8001
```

## 部署检查

部署前：

- [ ] `.env`、密钥和本地数据未进入打包内容。
- [ ] 后端通过编译和单元测试。
- [ ] 前端通过 typecheck、lint 和 build。
- [ ] 数据库有备份和回滚方案。

部署后：

- [ ] `/health` 返回正常。
- [ ] `docker compose ps` 中四个服务状态正常。
- [ ] `alembic current` 与代码预期一致。
- [ ] 登录、打卡、专注、花园、AI 会话、知识库问答完成 smoke test。

## 数据库迁移

```bash
alembic revision -m "describe change"
alembic upgrade head
```

不要修改已经应用的迁移。手工修改 schema 后，必须检查实际索引和表状态，不能只依赖 Alembic 版本号。