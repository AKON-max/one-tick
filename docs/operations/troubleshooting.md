# Troubleshooting

## 后端无法启动

优先检查：

1. `.env` 是否包含非法或拼写错误的配置。
2. `DATABASE_URL` 是否指向可用的 PostgreSQL。
3. 数据库是否安装了 pgvector 扩展。
4. 当前迁移版本是否正确。

```bash
alembic current
alembic upgrade head
docker compose logs --tail=100 app
```

## 前端无法访问 API

```text
浏览器 → Nginx /api/* → FastAPI
Next.js 服务端 fetch → API_INTERNAL_URL
```

检查：

- `API_INTERNAL_URL` 是否指向容器内的 `http://app:8001`。
- Nginx upstream 是否为 `app:8001`。
- `docker compose ps` 中 app 是否 healthy。

## AI 首字延迟很长

- 查看模型池日志，确认实际使用的模型和 tier。
- 检查是否触发了工具循环。
- 检查 provider 是否限流或额度耗尽。
- 不要只看检索耗时；LLM 首 token 通常是秒级。

## AI 回答为空

- 检查 provider 配额。
- 检查流式响应是否被代理缓冲。
- 检查 Nginx 的 `proxy_buffering` 和超时。
- 查看 `docker compose logs app` 中的 provider 异常。

## RAG 回答不准确

按顺序检查：

1. 文档是否成功切块并写入 `DocumentChunk`。
2. embedding 是否成功生成，数量是否为 0。
3. 用户过滤条件是否正确。
4. HNSW 索引是否存在。
5. 召回结果是否包含正确来源。
6. 评测语料和问题是否与线上场景一致。

```sql
SELECT indexname FROM pg_indexes WHERE tablename = 'documentchunk';
```

## 小岛树数量不变化

检查：

- 专注会话是否写入 `studyrecord`。
- `Garden.energy` 是否增加。
- 浇水是否成功扣除 25 能量。
- `wateredCount` 是否超过最高阶段。
- `maturedCount` 是否增加。
- 前端传入的 `treeCount` 是否来自最新 summary。

## WebSocket 连接失败

- token 或 Cookie 是否有效。
- Nginx 是否配置 `Upgrade` 和 `Connection`。
- 心跳是否超时。
- 是否误用了多实例部署；当前连接集合只存在于单个进程。

## 构建内存不足

- 限制 Docker / WSL 内存。
- 前端已限制 Next.js 构建并发。
- 清理 `.next` 后重试。
- 确认不要扫描 `node_modules` 或本地缓存。