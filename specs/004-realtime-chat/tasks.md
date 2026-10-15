# Tasks: Realtime Chat

## Phase 1 · 连接与协议

- [x] T-WS-00 定义消息类型常量与 `to_dto` / `iso_z` 序列化（`ws/protocol.py`）
- [x] T-WS-01 `/ws` 握手鉴权，失败 `close 1008`
- [x] T-WS-02 `ready` 消息与用户信息下发
- [x] T-WS-03 连接注册/注销与 `presence` 广播（`ws/room.py`）
- [x] T-WS-13 nginx `/ws` 的 `Upgrade` / `Connection` / 读超时配置

## Phase 2 · 治理

- [x] T-WS-04 消息长度上限 2000 与 `error` 返回
- [x] T-WS-05 滑动窗口限流（60000ms / 30 条）
- [x] T-WS-06 `clientId` 去重环（容量 200，超出淘汰最旧）
- [x] T-WS-07 全局心跳任务与 2× 超时回收
- [x] T-WS-14 `ping` → `pong` 并刷新 `last_seen`
- [x] T-WS-15 非法 JSON / 未知类型返回 `error` 且不断连

## Phase 3 · 消息与广播

- [x] T-WS-08 落库 `ChatMessage(role=user)`，昵称头像取数据库最新值
- [x] T-WS-09 落库后广播 `message`
- [x] T-WS-16 `createdAt` 统一为 ISO 8601 UTC 带 `Z`

## Phase 4 · @AI

- [x] T-WS-10 `extract_ai_prompts`：`@温柔宝` / `@嘴欠宝` / `/ai` 解析
- [x] T-WS-11 同角色在一条消息内去重
- [x] T-WS-12 `handle_ai` 异步任务：embedding → 检索 → 拒答 → LOW 档流式
- [x] T-WS-17 `ai:start` / `ai:delta` / `ai:done` 下发与 `ChatMessage(ai)` + `AIHistory` 落库
- [x] T-WS-18 AI 生成不阻塞用户消息广播

## Phase 5 · 验证

- [x] T-TEST-WS-01 `tests/test_ws_ai_mentions.py` 四用例
- [x] T-TEST-WS-02 `scripts/test_ws.py` 握手与广播冒烟
- [x] T-TEST-WS-03 长度 / 限流 / 去重 / 心跳的手工复现步骤
- [x] T-TEST-WS-04 CI 执行编译与单测

## Follow-up

- [ ] T-PROD-WS-01 广播外置（跨节点发布订阅）
- [ ] T-PROD-WS-02 连接与在线人数指标
- [ ] T-PROD-WS-03 多房间与私聊 UI
- [ ] T-PROD-WS-04 消息内容审核与更细的角色权限

## Traceability

| 需求 | 任务 | 验证 |
|---|---|---|
| R-WS-01 | T-WS-01 | 未登录用例 |
| R-WS-02 | T-WS-02 | 协议用例 |
| R-WS-03 | T-WS-03 | presence 用例 |
| R-WS-04 | T-WS-13 | 配置检查 |
| R-WS-05 | T-WS-04 | 长度用例 |
| R-WS-06 | T-WS-05 | 限流用例 |
| R-WS-07 | T-WS-06 | 幂等用例 |
| R-WS-08 | T-WS-07 | 心跳用例 |
| R-WS-09 | T-WS-14 | 协议用例 |
| R-WS-10 | T-WS-15 | 容错用例 |
| R-WS-11 | T-WS-08 | 落库检查 |
| R-WS-12 | T-WS-09 | 广播用例 |
| R-WS-13 | T-WS-16 | 格式断言 |
| R-WS-14 | T-WS-10 | `test_ws_ai_mentions.py` |
| R-WS-15 | T-WS-11 | `test_ws_ai_mentions.py` |
| R-WS-16 | T-WS-18 | 时序检查 |
| R-WS-17 | T-WS-17 | 协议用例 |
| R-WS-18 | T-WS-12 | 降级用例 |
