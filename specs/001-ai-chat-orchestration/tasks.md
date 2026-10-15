# Tasks: AI Chat Orchestration

## Phase 1 · 契约与数据模型

- [x] T-AI-00 定义 `Conversation` / `ConversationMessage` / `AIHistory` / `TokenUsage` 模型与索引
- [x] T-AI-01 定义鉴权入口（Cookie + Bearer）与 401 语义
- [x] T-AI-02 定义用量检查入口 `assert_interactive_usage_allowed`
- [x] T-AI-03 定义上下文常量 `MAX_CONTEXT_ROUNDS=20` / `MAX_CONTEXT_MESSAGES=40`
- [x] T-AI-04 定义 `ChatRequest` 契约（messages / conversationId / deepThink / studioContext）

## Phase 2 · 运行时

- [x] T-AI-05 会话解析与新建，标题由 LOW 档生成并支持回落
- [x] T-AI-06 服务端上下文截断
- [x] T-AI-07 长期记忆载入与注入
- [x] T-AI-08 工具注册表与 `build_tool_specs` 交集过滤
- [x] T-AI-09 工具体系：`safe_execute`、未知工具结构化失败、用户域闭包
- [x] T-AI-10 有界 Agent Loop（最多 4 轮，必须产出最终文本）
- [x] T-AI-11 模型池分档 + 403/429 区分 + `max_retries=0`
- [x] T-AI-12 流式响应与独立会话落库
- [x] T-AI-13 `X-Conversation-Id` 响应头
- [x] T-AI-14 Token 记账

## Phase 3 · 验证

- [x] T-TEST-AI-01 契约常量测试（`tests/test_ai_contract.py`）
- [x] T-TEST-AI-02 模型池 403 / 429 行为验证（`scripts/test_model_pool.py`）
- [x] T-TEST-AI-03 鉴权冒烟（`scripts/test_auth.py`）
- [x] T-TEST-AI-04 对话流式冒烟（`scripts/test_chat.py`）
- [x] T-TEST-AI-05 CI 执行 compileall + unittest

## Follow-up

- [ ] T-PROD-AI-01 模型池状态外置共享存储，多实例一致
- [ ] T-PROD-AI-02 为每一档模型补 Provider Mock 契约测试
- [ ] T-PROD-AI-03 输出模型错误率与切换次数指标
- [ ] T-PROD-AI-04 明确的整档不可用降级文案与前端呈现

## Traceability

| 需求 | 任务 | 验证 |
|---|---|---|
| R-AI-01 | T-AI-01 | 契约测试 + 401 用例 |
| R-AI-02 | T-AI-02 | 超限用例 |
| R-AI-03 | T-AI-03 / T-AI-06 | `test_ai_contract.py` |
| R-AI-04 | T-AI-07 | 越权用例 |
| R-AI-05 | T-AI-10 | Agent Loop 契约 |
| R-AI-06 | T-AI-11 | `test_model_pool.py` |
| R-AI-07 | T-AI-12 | 流式用例 |
| R-AI-08 | T-AI-13 | 响应头断言 |
| R-AI-09 | T-AI-04 | 契约常量 |
| R-AI-10 | T-AI-04 | 契约常量 |
| R-AI-11 | T-AI-05 | 回落用例 |
| R-AI-12 | T-AI-09 | 工具契约 |
| R-AI-13 | T-AI-14 | 用量写入检查 |
| R-AI-14 | T-AI-02 | 配置用例 |
| R-AI-15 | T-AI-08 | Schema 检查 |
| R-AI-16 | T-AI-08 | 注册表检查 |
| R-AI-17 | T-AI-05 | 会话用例 |
