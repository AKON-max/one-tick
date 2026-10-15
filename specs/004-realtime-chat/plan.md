# Technical Plan: Realtime Chat

| 字段 | 值 |
|---|---|
| Spec | `004-realtime-chat` |
| Status | implemented |
| Components | `ws/chat.py`、`ws/room.py`、`ws/protocol.py`、`ws/ai_chat.py`、`models/chat.py`、`routers/chat.py`、`nginx.conf` |
| State | 连接表、限流窗口、去重环均为进程内；单实例部署 |
| Rollback | 回退应用镜像与 nginx 配置；消息表向前兼容 |

## 1. 连接生命周期

```python
@router.websocket("/ws")
async def ws_chat(websocket: WebSocket):
    token = websocket.query_params.get("token") or websocket.cookies.get(SESSION_COOKIE_NAME) or websocket.cookies.get(SESSION_COOKIE_LEGACY)
    user = decode_token_or_none(token)
    if not user:
        await websocket.close(code=1008); return

    conn = Connection(ws=websocket, user_id=user.id, last_seen=now_ms(),
                      window_start=now_ms(), message_count=0, seen_client_ids=OrderedDict())
    register(conn)
    await send(conn, {"type": "ready", "user": {...}})
    await broadcast_presence()
    try:
        while True:
            msg = json.loads(await websocket.receive_text())
            await handle_message(conn, msg)
    except WebSocketDisconnect:
        pass
    finally:
        unregister(conn)
        await broadcast_presence()
```

## 2. 队列与广播

`room.py` 维护在线连接集合与广播函数。广播遍历当前在线连接逐个 `send_text`，单个连接发送失败只移除该连接，不中断整轮广播。

## 3. 握手鉴权

- token 来源顺序：query 参数 → 会话 Cookie → 历史 Cookie 名。
- 解析失败或用户不存在 → `close 1008`。
- 未登录连接不会进入 `room`，因此不参与广播也不计入在线人数。

## 4. 滑动窗口限流与去重

```python
def _check_rate_limit(conn) -> bool:
    now = now_ms()
    if now - conn.window_start > settings.RATE_LIMIT_WINDOW_MS:   # 60000
        conn.window_start = now
        conn.message_count = 0
    conn.message_count += 1
    return conn.message_count <= settings.RATE_LIMIT_MAX          # 30
```

去重：`seen_client_ids` 是有序集合，容量 `MAX_SEEN_CLIENT_IDS=200`，超容量时 `pop()` 淘汰最旧的（`OrderedDict`/`set` 语义下最先进者）。命中重复直接 `return`，**在落库与广播之前**，避免任何副作用。

判定顺序固定为：长度 → 限流 → 去重 → 落库 → 广播 → @AI。顺序有意义：先做便宜的拒绝，再做昂贵的副作用。

## 5. 心跳

`heartbeat_loop()` 是应用启动时创建的全局 `asyncio` 任务：

```python
timeout_ms = settings.HEARTBEAT_INTERVAL_MS * 2      # 60000
while True:
    await asyncio.sleep(settings.HEARTBEAT_INTERVAL_MS / 1000)
    now = now_ms()
    for c in all_connections():
        if now - c.last_seen > timeout_ms:
            await close_and_unregister(c)
    await broadcast_presence()
```

关键点：**不依赖客户端是否会发 pong**。浏览器断电或直接关页面不会发送 close 帧；只有服务端按 `last_seen` 超时主动关闭，才能回收半开连接。

## 6. 消息落库与广播

- 落库前用数据库中的最新昵称与头像构造 DTO，而不是用连接建立时的快照——用户中途改头像后，连接里存的是旧值。
- DTO 的 `role` 只取 `user` / `assistant` / `system` 三值。
- `createdAt` 用 `iso_z()` 转成带 `Z` 的 UTC 字符串。
- 落库成功后广播；广播失败不影响落库结果。

## 7. @AI 触发

- `extract_ai_prompts(content)` 返回 `[(role, prompt)]`：
  - 命中 `温柔宝` → `gentle`；
  - 命中 `嘴欠宝` 或 `/ai` → `snarky`；
  - 同一角色在一条消息中出现多次只保留一个。
- 触发后 `asyncio.create_task(handle_ai(...))`，立刻返回，不阻塞广播路径。
- `handle_ai` 内：embedding → 检索 → 拒答判断 → 拼 Prompt → LOW 档流式生成 → `ai:start` / `ai:delta` / `ai:done` → 落库 `ChatMessage` 与 `AIHistory`。

## 8. Nginx 配置

```nginx
location /ws {
    proxy_pass http://app:8001;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_read_timeout 3600s;
    proxy_send_timeout 3600s;
}
```

缺 `Upgrade` / `Connection` 会导致握手 426；读超时保持默认 60s 会在心跳正常的情况下定期掐断长连接。

## 9. 风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| 半开连接泄漏 | 内存与连接数持续上涨 | 服务端独立心跳 + 2× 超时回收 |
| 消息刷屏 | 广播放大，全员卡顿 | 滑动窗口限流 30/60s |
| 重复消息 | 重复落库 + 重复 AI 消耗 | `clientId` 去重环（200） |
| 匿名连接 | 资源被无成本占用 | 握手 `close 1008` |
| 头像/昵称陈旧 | 前端显示过期信息 | 落库时取数据库最新值 |
| AI 阻塞广播 | 用户消息延迟可见 | 异步任务 + 立即返回 |
| 单实例连接表 | 无法水平扩展 | 已声明为已知边界 |
| nginx 缓冲流式响应 | AI 增量一次性到达 | `/api/` 关闭 `proxy_buffering` |

## 10. 验证

- `tests/test_ws_ai_mentions.py`：`@温柔宝` / `/ai` / 同角色去重 / 命令形式四个用例。
- `scripts/test_ws.py`：握手、`ready`、广播、AI 回复链路。
- 手工冒烟：脚本连发 31 条验证限流；重复 `clientId` 验证去重；静默 60 秒验证心跳回收。

## 11. 回滚

回退应用镜像与 `nginx.conf` 即可。`ChatMessage` 结构不变，历史消息保持可读。
