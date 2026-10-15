# Tasks: Agent Runtime and Approval

## Phase 1 · 数据与契约

- [x] T-AGENT-00 定义 `AgentRun` / `AgentStep` / `AgentApproval` / `AgentToolCall` / `AgentDecision` / `AgentSchedule` 模型
- [x] T-AGENT-01 `AgentRun.status` 七状态枚举
- [x] T-AGENT-02 `AgentStep` 的 `(runId, stepNumber)` 唯一约束与状态索引
- [x] T-AGENT-03 失败语义：Step 记 `error`，Run 记 `failed`
- [x] T-AGENT-08 `PlanDraft` / `TaskDraft` 的 Pydantic 范围约束
- [x] T-AGENT-13 `AgentRunResponse` 序列化契约

## Phase 2 · 运行时

- [x] T-AGENT-04 Step1 `observe(user_id)` 只读上下文收集
- [x] T-AGENT-05 Step2 `analyze()`：HIGH 档 + JSON 解析 + 重试一次
- [x] T-AGENT-09 `fallback_analysis()` 规则兜底
- [x] T-AGENT-14 Step3 `plan`：findings / actions 写 `AgentApproval`
- [x] T-AGENT-06 Step4 `execute`：逐条执行 action，失败隔离
- [x] T-AGENT-07 通知「同类当日一条」节流
- [x] T-AGENT-10 `AgentDecision` 记录每条 action 结果
- [x] T-AGENT-15 `summary` 生成

## Phase 3 · 工具与权限

- [x] T-AGENT-11 `create_agent_tools(user_id)`：`breakdownPlanTasks` / `getPlanTasks` / `updateTaskStatus` / `getTodayTasks`
- [x] T-AGENT-16 改写类工具的归属校验
- [x] T-AGENT-12 `/api/agent/cron/daily` 的 `CRON_SECRET` 校验
- [x] T-AGENT-17 运行查询、审批、取消的归属校验

## Phase 4 · 验证

- [x] T-TEST-AGENT-01 `PlanDraft` 上限用例（`tests/test_ai_contract.py`）
- [x] T-TEST-AGENT-02 Agent 端到端冒烟（`scripts/test_agent.py`）
- [x] T-TEST-AGENT-03 CASCADE 与唯一约束检查
- [x] T-TEST-AGENT-04 CI 执行编译与单测

## Follow-up

- [ ] T-PROD-AGENT-01 运行状态持久化队列，支持断点续跑
- [ ] T-PROD-AGENT-02 审批权限矩阵（哪些 action 可在什么风险等级下自动执行）
- [ ] T-PROD-AGENT-03 运行耗时与成功率指标
- [ ] T-PROD-AGENT-04 跨天/跨周计划调整的幂等收敛

## Traceability

| 需求 | 任务 | 验证 |
|---|---|---|
| R-AGENT-01 | T-AGENT-01 | 状态枚举测试 |
| R-AGENT-02 | T-AGENT-02 | 唯一约束 |
| R-AGENT-03 | T-AGENT-03 | 失败用例 |
| R-AGENT-04 | T-AGENT-13 | 响应契约 |
| R-AGENT-05 | T-AGENT-15 | 响应契约 |
| R-AGENT-06 | T-AGENT-04 | Observe 输出检查 |
| R-AGENT-07 | T-AGENT-05 | 契约测试 |
| R-AGENT-08 | T-AGENT-05 | 枚举校验 |
| R-AGENT-09 | T-AGENT-06 | 枚举校验 |
| R-AGENT-10 | T-AGENT-06 | 部分失败用例 |
| R-AGENT-11 | T-AGENT-07 | 节流用例 |
| R-AGENT-12 | T-AGENT-08 | `test_ai_contract.py` |
| R-AGENT-13 | T-AGENT-08 | 契约测试 |
| R-AGENT-14 | T-AGENT-08 | 契约测试 |
| R-AGENT-15 | T-AGENT-08 | 枚举校验 |
| R-AGENT-16 | T-AGENT-08 | 契约测试 |
| R-AGENT-17 | T-AGENT-09 | 兜底用例 |
| R-AGENT-18 | T-AGENT-14 | 落表检查 |
| R-AGENT-19 | T-AGENT-10 | 落表检查 |
| R-AGENT-20 | T-AGENT-17 | 越权用例 |
| R-AGENT-21 | T-AGENT-16 | 越权用例 |
| R-AGENT-22 | T-AGENT-12 | 入口用例 |
