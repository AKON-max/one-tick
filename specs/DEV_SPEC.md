# Developer Specification (DEV_SPEC)

> 本文档是 One-Tick（一刻 · AI 自习室）的项目级设计规格，描述系统目标、设计原则、技术选型、模块边界、关键链路、数据契约、参数决策依据、测试方案和演进路线。
>
> - 功能级行为契约见 `specs/<capability>/spec.md`；
> - 实现路径与风险见同目录的 `plan.md`；
> - 工作拆分与需求追溯见同目录的 `tasks.md`；
> - 影响长期维护的取舍记录在 `docs/adr/`。
>


## 目录

1. 项目概述
2. 设计理念
3. 核心能力
4. 技术选型
5. 系统架构与模块设计
6. 请求生命周期与关键链路
7. 数据模型与数据契约
8. RAG 摄取、检索与精排
9. Agent Runtime 与工具调用
10. 模型池与容错降级
11. Realtime 长连接治理
12. 安全与用量治理
13. 测试与评估
14. 部署与运行
15. 工程规范
16. 交付里程碑
17. 已知边界
18. 演进路线
19. 术语表

---

## 1. 项目概述

### 1.1 定位

One-Tick 是一个面向个人学习场景的「计划 → 专注 → 打卡 → 复盘」闭环产品。它的目标不是把页面堆起来，而是让上一步的行为成为下一步状态的输入，并把 AI 放在这条数据链路的中间：AI 读的是真实学习数据，写回的也是真实业务对象。

四个服务、一套 Compose：

| 服务 | 技术 | 核心职责 |
|---|---|---|
| `nginx` | nginx:alpine | 同域入口；`/api/*` 与 `/ws` 分流到 FastAPI，其余交给 Next.js |
| `app` | Python + FastAPI + SQLAlchemy + Alembic | 65 个 REST 端点、1 条 WebSocket 端点、AI 编排、鉴权、事务边界 |
| `web` | Next.js App Router + React + React Three Fiber | 15 个页面、Server Actions、3D 小岛场景 |
| `db` | PostgreSQL 16 + pgvector | 业务事实、会话消息、长期记忆、知识库向量 |

`app` 是唯一写入业务库的服务；`web` 通过同域 `fetch` 和 Server Actions 访问 `/api/*`，不直连数据库。

### 1.2 要解决的问题

| 问题 | 常见做法 | 本系统的做法 |
|---|---|---|
| 立了 Flag 但不会拆 | 让用户自己写任务清单 | 计划 Markdown + `plan_split` 服务 + Agent `breakdownPlanTasks` 工具，拆出可执行任务 |
| 计划任务与文档不同步 | 文档和任务各记一份 | `plan_sync` 从「## 任务安排」段落的 checkbox 生成任务，`source_hash` 保证幂等 |
| 学完不知道干了什么 | 周报靠回忆 | Agent Runtime 每日 Observe → Analyze → Plan → Execute，产出 findings / actions 并落表 |
| 问自己的资料答不上来 | 模型凭记忆编 | pgvector + HNSW 检索 + 本地余弦精排 + 相似度阈值拒答 |
| 免费额度用完功能全挂 | 单模型单点 | 模型池分档 + 403 永久耗尽 / 429 冷却 60s 自动切流 |
| 长连接把资源拖死 | 直接收发消息 | 握手鉴权 + 心跳 + 滑动窗口限流 + clientId 去重 + presence 广播 |
| 出了问题只能翻日志 | 靠 print 排查 | Agent 运行、步骤、工具调用、决策全部落表，前端可还原时间轴 |

### 1.3 成功标准

- 游客免注册即可进入并跑通「建计划 → 拆任务 → 专注 → 打卡 → 统计」主流程。
- AI 对话能在工具调用失败、模型额度耗尽、模型限流三种情况下仍然给出最终文本。
- 知识库没有答案时系统明确说「知识库没有」，而不是编造。
- Agent 的每一次运行都能在数据库里还原到步骤级，包括失败在哪一步。
- 连接断开、消息重复、消息刷屏三种异常都有对应的确定性处理路径。
- 每个 P0 需求都有单元测试、评测脚本或可复现的手工步骤之一作为验收方式。

### 1.4 非目标

- 不声明多实例共享状态：模型池耗尽/冷却表、WebSocket 连接表都在进程内。
- 不提供生产级 SLA、容量承诺和压测报告。
- 不实现真实的多租户隔离、组织权限和计费。
- 不把 Dashboard、监控告警、分布式追踪说成已有能力。
- 不做数据仓库、离线特征平台或模型微调。

---

## 2. 设计理念

### 2.1 业务事实优先，向量与业务同库

检索和对话都必须建立在业务事实上，因此系统不引入独立的向量数据库：向量的生命周期跟着业务行走。

理由：

1. 事务一致：`DocumentChunk` 行删掉就是向量删掉，删用户 CASCADE 一次清干净，没有双写补偿。
2. 运维成本：会 PostgreSQL 就会管这一套，不需要额外一套集群和备份策略。
3. 过滤自由：`userId`、`sourceName` 这类过滤条件和向量排序能在同一条 SQL 里完成。
4. 规模匹配：当前语料不到一万块，实测 HNSW 检索 P50 6.7ms，独立向量库带来的收益远小于它带来的运维负担。

这条原则有边界：语料量或并发上到当前方案的十倍以上时，重新评估拆分，见 §18。

### 2.2 模型不可用是运行时常态，不是异常

模型调用的失败不是「偶发 bug」，而是每天都会发生的正常事件：免费额度耗尽、限流、超时、供应商抖动。所以模型池把两类失败区分开处理，并让调用方对模型选择完全不感知：

- 额度耗尽（403 / InsufficientBalance）：本进程内标记为不可用，不再重试。
- 限流（429 / rate limit）：冷却 60 秒后自动恢复。

调用方只写 `completions_with_fallback("high", ...)`，不需要知道当前用的是哪一个供应商、哪一个模型。

### 2.3 长连接必须被治理，否则一定会泄漏

HTTP 是请求-响应，连接的生命周期短、好回收。WebSocket 一旦连上就是长生命周期对象，如果不做治理，线上必然出现三件事：半开连接泄漏、消息刷屏拖垮广播、重复消息导致重复落库和重复 AI 回复。因此握手鉴权、心跳、限流、去重、presence 广播是**一起**做的最小集合，不是可选项。

### 2.4 AI 的所有状态可追溯

一次 Agent 运行包含多个步骤、多次工具调用和若干条待确认决策。如果只把结果写进通知，出了问题就只能翻日志。因此系统把 `AgentRun / AgentStep / AgentToolCall / AgentDecision` 全部落表，`AgentStep` 用 `(runId, stepNumber)` 唯一约束保证顺序，运行失败时 `status=failed` 且带 `error`，前端时间轴能指出是哪一步坏掉。

### 2.5 克制选型，降低长期维护成本

不引入 LangChain / LangGraph，不引入 Redis，不引入独立向量库。判断标准是：这个依赖是否解决了我**当前**必须解决的问题，且它的复杂度是否小于它替换掉的代码。

Agent 的流程是固定四步顺序，执行阶段最多四轮工具调用，这是线性状态机，不需要图引擎的表达力。引入重型框架后，调试要穿过多层 SDK 栈，升级要跟随上游 Breaking Change，而收益只是少写一些本来也不复杂的编排代码。

### 2.6 质量必须可回归，参数必须停在曲线平台区

- 检索行为的每次调整都要有评测记录，口径包含语料规模、问题数量、索引参数、是否含无答案问题。
- 超参数不取「看起来更大就更好」的值，而是取「指标曲线进入平台区」的点。
- 「修缺陷」和「做优化」严格分开表述：旧检索 `LIMIT 1000` 让语料超过 1000 块后更早的内容永远进不了候选集，这是正确性缺陷，不是调优空间，不允许包装成性能优化。

### 2.7 一人可运维

每个新增组件都要回答：出问题时一个人怎么定位、怎么恢复。当前答案是三层：nginx access log、FastAPI 结构化输出、28 张业务表的状态。达不到这个标准的组件不进生产路径。

---

## 3. 核心能力

### 3.1 学习闭环

| 能力 | 数据对象 | 关键约束 |
|---|---|---|
| 计划 | `Plan` | Markdown 文档 + 「## 任务安排」段落，是任务同步的唯一来源 |
| 任务 | `PlanTask` | `source_hash` 幂等：同一计划同一拆解输入只拆一次 |
| 待办 | `Todo` | 按自然日归属，未完成在前 |
| 打卡 | `Checkin` | 幂等依赖应用层先查后写 |
| 专注 | `StudyRecord` | 每次会话结束落一条，统计走 SQL 聚合，不维护汇总表 |
| 统计 | 聚合视图 | 打卡天数、连续天数、计划进度、专注分钟 |

### 3.2 AI 对话编排

`POST /api/ai` 与 `POST /api/ai/chat` 是多轮对话入口，单次请求在服务端完成：鉴权 → 用量检查 → 会话解析 → 上下文截断 → 长期记忆注入 → 工具注册 → 有界 Agent Loop → 模型池流式生成 → 消息落库 → 记忆抽取。

对外可观察的行为：

- 响应是 `text/plain` 流，逐增量返回，不是一次性 JSON。
- 响应头 `X-Conversation-Id` 回传本次会话 ID。
- 请求可带 `deepThink`（要求模型先梳理再作答）与 `studioContext`（把用户正在编辑的文档注入上下文）。
- 单次请求的工具调用最多 4 轮，且**无论是否触发工具，都必须产出最终文本**。

### 3.3 RAG 检索

知识库能力分两段：

- 摄取：文档上传 → 解析 → 分块 → embedding → `DocumentChunk`。
- 检索：问题 embedding → pgvector Top-20 → 本地余弦精排 Top-5 → 拼 Prompt → 引用来源。

拒答：Top-1 相似度低于阈值时明确回答「知识库中未找到相关内容」，区分「知识库没有」和「我按通用知识补充」。

### 3.4 Agent Runtime

自研四步运行时，不依赖第三方 Agent 框架：

```text
Observe  → 收集打卡、活跃计划、任务统计、今日专注、相关长期记忆
Analyze  → HIGH 档模型输出结构化 JSON：status / findings / actions
Plan     → findings 与 actions 写入 AgentApproval，等待或自动执行
Execute  → 逐条 action 调用对应工具，结果写 AgentDecision
```

五种 action：`ADJUST_PLAN`、`CREATE_TASK`、`SEND_REMINDER`、`GENERATE_REPORT`、`ENCOURAGE`。
四种 status：`on_track`、`need_attention`、`need_adjustment`、`at_risk`。

模型不可用时走 `fallback_analysis`：基于阈值规则的保底分析，保证 Agent 不会因为模型故障彻底不产出。

### 3.5 实时聊天室

单房间 WebSocket，`/ws?token=...`（token 也可放 Cookie）：

- 服务端消息类型：`ready`、`message`、`ai:start`、`ai:delta`、`ai:done`、`presence`、`pong`、`error`。
- 客户端消息类型：`message`（带 `clientId`）、`ping`。
- AI 角色：`gentle`（温柔宝）、`snarky`（嘴欠宝），也支持 `/ai` 命令形式，同一角色一轮内去重。
- AI 回复走异步任务，不阻塞用户消息的广播。

### 3.6 鉴权与用量

- 密码：scrypt 加盐哈希，存储格式 `salt:hash`，参数 `N=16384, r=16, p=1`，显式放开 `maxmem`。
- 会话：HS256 JWT，有效期 7 天，Cookie 与 `Authorization: Bearer` 双入口。
- 用量：`AI_TOKEN_LIMIT` 按自然日统计，交互式入口超限抛出 `UsageLimitError` 并返回友好提示；embedding 不计入用户配额。

---

## 4. 技术选型

选型按三个要素打分：① 语言生态 ② 需求匹配 ③ 克制程度（复杂度是否小于它替换掉的代码）。

| 领域 | 候选 | 最终选择 | 放弃理由 |
|---|---|---|---|
| 后端语言 | Go / Node / Python | Python | LLM SDK 与 pgvector 生态最完整；AI 密集场景迭代最快 |
| Web 框架 | Django / Flask / FastAPI | FastAPI | 原生 WebSocket + Pydantic 契约 + 依赖注入三件套齐备，65 REST + 1 WS 规模不必引入 Django 的整套心智 |
| ORM / 迁移 | Prisma / Tortoise / SQLAlchemy + Alembic | SQLAlchemy 2.0 + Alembic | 需要原生支持 pgvector 扩展与 HNSW 索引的迁移能力 |
| 数据库 | MongoDB / MySQL / PostgreSQL | PostgreSQL 16 | 关系约束、CASCADE、JSON 列与向量扩展都在这一个库里 |
| 向量存储 | Chroma / Milvus / Qdrant / pgvector | pgvector | 见 §2.1；< 1000 万条量级总拥有成本最低 |
| 向量索引 | IVFFlat / HNSW | HNSW | 语料是增量入库，IVFFlat 需要预先训练聚类中心，新增数据会让中心偏移，得定期重建 |
| Agent 框架 | LangChain / LangGraph / 自研 | 自研 Runtime | 固定四步 + 最多四轮工具调用是线性状态机；调试可直达 Tool 函数，不受上游 Breaking Change 影响 |
| 模型接入 | 单 Provider / 多 Provider 池 | 多 Provider 分档池 | 单点额度耗尽会让全部 AI 功能不可用 |
| 实时通信 | SSE / Socket.IO / 原生 WebSocket | 原生 WebSocket | 需要双向消息与异步广播；SSE 单向，Socket.IO 多一层协议 |
| 前端 | Vue3 / React SPA / Next.js App Router | Next.js App Router | 15 个页面 + Server Actions + 3D 场景，SSR 首屏体验对游客入口重要 |
| 部署 | K8s / Serverless / Docker Compose | Docker Compose + 单机 | 四服务单机 2C4G 够用；K8s 的运维量对一人项目不成立 |

选型的反面约束同样明确：任何要求「再引入一套集群」的方案，在它解决的问题量级到来之前都不采纳。

---

## 5. 系统架构与模块设计

### 5.1 部署拓扑

```text
Browser
  │
  ▼
Nginx :80
  ├── /api/*        → FastAPI :8001   （proxy_buffering off，流式直通）
  ├── /ws           → FastAPI :8001   （Upgrade/Connection，读超时 3600s）
  ├── /health       → FastAPI :8001
  └── /             → Next.js :3000   （Host 用 $http_host 保留端口）
                        │
                        └── server-side fetch → http://app:8001

FastAPI :8001 ──► PostgreSQL 16 + pgvector :5432
```

同域架构的两个直接收益：

1. 前端 52 处 `fetch` 使用相对路径，不需要配置 API Base URL，也不需要跨域头。
2. 浏览器 Cookie 天然随请求发送，会话不需要在两端各维护一份。

### 5.2 后端分层

| 层 | 目录 | 职责 | 不允许 |
|---|---|---|---|
| 协议层 | `app/routers/`、`app/ws/` | 鉴权、参数校验、HTTP / WebSocket 协议、错误映射 | 承载业务规则 |
| 服务层 | `app/services/` | 统计聚合、计划拆分、计划同步、通知、用量、OSS | 直接依赖请求线程 Session |
| AI 层 | `app/ai/` | 模型池、RAG、记忆、Agent Runtime、工具注册表 | 越权访问他人数据 |
| 模型层 | `app/models/` | SQLAlchemy ORM、约束与索引 | 包含业务分支 |
| 迁移层 | `alembic/versions/` | Schema 演进、pgvector 扩展与 HNSW 索引 | 事后手工 ALTER 而不落迁移 |

依赖方向自下而上单向：AI 层可以调模型层，模型层不反向调 AI 层；`routers` 不直接写 SQL，`services` 不处理 HTTP。

### 5.3 目录结构

```text
app/
├── main.py                 # 应用装配：全部 REST 路由 + /ws + 生命周期
├── core/
│   ├── config.py           # 环境变量集中管理（Pydantic Settings）
│   └── security.py         # scrypt 哈希、JWT 签发校验、当前用户注入
├── db/session.py           # 引擎、SessionLocal、Base
├── models/                 # 28 张表的 ORM 定义
│   ├── base.py study.py garden.py knowledge.py chat.py agent.py misc.py
├── routers/                # 18 个 router 模块，65 个 REST 端点
├── services/               # study_stats / plan_split / plan_sync / notification / usage / oss / onboard
├── ai/
│   ├── model_pool.py       # 分档链条、耗尽/冷却、token 记账
│   ├── memory.py           # 长期记忆抽取、排序、去重、淘汰
│   ├── rag/                # chunk / client / retriever / search
│   ├── agent/              # runtime / service / types / decisions / report / weekly
│   └── tools/              # study_tools / todo_tools / rag_tools / agent_tools
└── ws/                     # protocol / room / chat / ai_chat
alembic/versions/           # 0001_initial → 0004_rag_vector_index
scripts/rag_eval/           # 评测：ingest / build_questions / eval_rag / eval_e2e / sweep_ef / teardown
frontend/                   # Next.js App Router
specs/                      # 本规格与功能级契约
docs/                       # 架构、AI 工程、测试、运维、ADR
tests/                      # 确定性单元测试
```

### 5.4 模块职责

| 模块 | 负责 | 不负责 |
|---|---|---|
| 认证与权限 | 注册/登录/改密、JWT 签发与校验、scrypt 哈希、当前用户注入 | 业务对象可见性（由业务查询的 `userId` 过滤承担） |
| 学习核心 | 计划、任务、待办、打卡、专注、统计 | 拆任务、生成提醒（AI 层与 services 承担） |
| AI 子系统 | 模型池、Agent Runtime、14 个工具、RAG、记忆 | 页面渲染、UI 交互 |
| 聊天与群聊 | WS 连接生命周期、广播、消息持久化、@AI 触发、在线人数 | AI 回复正文（`ws/ai_chat.py` 单独负责） |
| 知识与文档 | 文档上传、分块入库、文档与模板生命周期 | 向量化与近邻排序（`ai/rag/` 负责） |
| 运维与通知 | 站内通知节流、每日用量记账、OSS 直传、Agent 定时调度 | 业务决策 |

### 5.5 AI 子系统五件套

1. **model_pool** — 对下管理两个供应商共 15 个模型条目，对上只暴露 `completions_with_fallback(tier)` 与 `embedding_with_fallback()`。
2. **agent/runtime** — 四步状态机 + 四张落表，每次运行一定有持久化 `run_id`。
3. **ai/tools** — 14 个工具分四类：study（5）、todo（4）、rag（1）、agent（4），全部为单一用户创建的用户域闭包。
4. **ai/rag** — chunk 分块 / client 向量化 / retriever 数据库 Top-K / search 精排与拒答，四层各自可单独测试。
5. **memory** — 长期记忆的向量近邻召回与冷淘汰更新，保证「考研」「找工作」这类长期目标不丢。

---

## 6. 请求生命周期与关键链路

### 6.1 通用生命周期

```text
HTTP / WebSocket
  → 鉴权（Cookie 或 Bearer）        → 401
  → 参数校验（Pydantic）            → 422
  → 用量检查（交互式面）            → UsageLimitError
  → 业务服务（事务边界）
  → AI 层（可选）
  → Repository / pgvector
  → 响应（流式或 JSON）
  → 用量记账 / 消息落库 / 日志
```

每一层只处理自己那一层的失败，向上抛出带语义的异常，由协议层映射成状态码与用户可读提示。

### 6.2 链路一：AI 对话

```text
POST /api/ai
  → Depends(get_current_user) 解析 Cookie/Bearer
  → assert_interactive_usage_allowed(user_id)        # 超限 → 友好提示
  → 会话解析：无 conversationId 则新建，标题用 LOW 档生成
  → 上下文截断：只保留最近 20 轮（40 条），后端兜底
  → 注入长期记忆（向量近邻，按 importance 排序）
  → 注入 studioContext.document（文档工作室场景）
  → deepThink 打开时追加「先梳理再作答」指令
  → build_tool_specs() 注册工具（含 searchKnowledgeBase）
  → _run_agent_loop(max_rounds=4)
        ├ 每轮：模型流式返回 → 若产生 tool_calls 则执行并回填
        └ 无论是否触发工具，最后一轮必须产出文本
  → StreamingResponse 逐增量下发，响应头带 X-Conversation-Id
  → 独立 DB 会话落库 assistant 消息
  → 抽取长期记忆并写 TokenUsage
```

关键点：**落库用独立数据库会话**，不复用请求线程的 Session，避免流式生成期间长事务持锁。

### 6.3 链路二：Agent 每日巡检

```text
用户触发或 /api/agent/cron/daily（Bearer CRON_SECRET）
  → AgentRun(status=running, currentStep=0)
  → Step1 Observe（kind=observe）
       收集：打卡 streak、活跃计划与进度、待办、今日专注分钟、20 条相关记忆
       Step.status=completed，output 存统计摘要
  → Step2 Analyze + Plan（kind=analyze）
       HIGH 档模型 → JSON { status, findings[], actions[] }
       模型不可用 → fallback_analysis 规则兜底
       findings / actions 写入 AgentApproval
  → Step3（kind=plan）记录产出条数
  → Step4 Execute（kind=execute）
       ADJUST_PLAN      → 发通知，引导用户到 /agent 页确认调整
       CREATE_TASK      → 找到首个活跃计划，创建 PlanTask
       SEND_REMINDER    → 创建 Notification（同类型当日只发一条）
       GENERATE_REPORT  → 生成学习小结 Markdown，落 Notification
       ENCOURAGE        → 生成鼓励文案
       每条 action 结果写 AgentDecision（status=pending 等用户确认）
  → AgentRun.status=completed，summary 一句话自然语言
```

任一步骤抛异常：当前 Step `status=failed` 且写入 `error`，`AgentRun.status=failed`，已完成的步骤保留，前端时间轴能直接定位坏在哪一步。

### 6.4 链路三：聊天室 @AI

```text
浏览器连 /ws（token 来自 query 或 Cookie）
  → 握手校验失败 → close 1008
  → 注册连接，broadcast presence
  → 客户端发 {type: "message", clientId, content}
       ① 长度检查 > 2000 → error
       ② 滑动窗口限流：60s 内第 31 条 → error rate_limited
       ③ clientId 已在 200 环内 → 丢弃
       ④ 落库 ChatMessage（用 DB 中最新的昵称与头像）
       ⑤ broadcast 原始消息给全部在线连接
       ⑥ 解析 @温柔宝 / @嘴欠宝 / /ai → role + prompt（同角色去重）
       ⑦ asyncio.create_task(handle_ai(...))   # 不阻塞广播
  → handle_ai 内：embedding → 检索 → 拒答判断 → 拼 Prompt
       → LOW 档流式生成 → 逐段 broadcast ai:delta → ai:done
       → 落库 AI 消息 + AIHistory + TokenUsage
```

### 6.5 链路四：文档摄取与检索

```text
摄取：上传 → 解析（txt/md/pdf/docx）→ split_text / split_markdown
      → embedding_with_fallback() → DocumentChunk(userId, sourceName, chunkIndex, content, embedding)
检索：问题 → embedding → SET LOCAL hnsw.ef_search = 100
      → ORDER BY embedding <=> query LIMIT 20
      → 本地余弦精排 → Top-5 → 阈值判断 → 拼 Prompt（带来源名）
```

### 6.6 链路五：长连接生命周期

```text
连接建立 → 注册 → ready
  ├ 心跳：全局独立 asyncio task，每 30s 扫描一次
  │        last_seen 超过 60s（2× 间隔）→ 服务端主动关闭
  ├ ping/pong：客户端可主动 ping，服务端回 pong 并刷新 last_seen
  └ 断开/异常 → 注销 → broadcast presence
```

心跳是**服务端独立任务**，不依赖客户端是否会发 pong。浏览器断电、直接关页面不会发 close 帧，只有服务端主动超时关闭才能回收半开连接。

---

## 7. 数据模型与数据契约

### 7.1 六大业务域

| 业务域 | 表 | 关键设计 |
|---|---|---|
| 认证 | `User` `Session` `Account` | 密码哈希 `salt:hash`；`account` 预留 OAuth 扩展 |
| 学习核心 | `Plan` `PlanTask` `Todo` `Checkin` `StudyRecord` | `PlanTask.source_hash` 幂等；统计走 SQL 聚合，不建汇总表 |
| Agent 治理 | `AgentRun` `AgentStep` `AgentApproval` `AgentToolCall` `AgentDecision` `AgentSchedule` `UserMemory` `AIHistory` | 运行-步骤-审批-工具调用-决策五级可还原；`UserMemory.embedding` 同库近邻召回 |
| 聊天与会话 | `ChatMessage` `Conversation` `ConversationMessage` | `ChatMessage` 存公共聊天室全量消息；私聊表已建但 UI 未开放 |
| 知识与文档 | `KnowledgeDoc` `Document` `DocumentChunk` `PlanTemplate` `DocumentTemplate` | `DocumentChunk.embedding` 为 `Vector(1024)` + HNSW；模板用于新用户冷启动 |
| 运营杂项 | `Notification` `TokenUsage` `AvatarChange` `Garden` | 通知「同日同类型只发一条」节流；`TokenUsage` 按 surface/user/tier 记账 |

除 `PlanTemplate` / `DocumentTemplate` 两张全局模板表外，所有业务表都带 `userId` 外键并 `ondelete="CASCADE"`。

### 7.2 Agent 治理域的数据契约

```text
AgentRun
  id, userId, mode, goal
  status            queued | running | awaiting_approval | completed | failed | cancelled | rejected
  currentStep, maxSteps（默认 12）
  summary, error, startedAt, completedAt, createdAt, updatedAt
  索引： (userId, updatedAt) (userId, status)

AgentStep
  id, runId, stepNumber, kind, status, title, detail
  input: JSON, output: JSON, error, startedAt, completedAt, createdAt
  唯一约束：(runId, stepNumber)           ← 顺序不可重复
  索引： (runId, status)

AgentApproval
  id, runId, stepId, action, status, payload(JSON), decisionReason, decidedAt, createdAt

AgentToolCall
  id, runId, stepId, name, input(JSON), output(JSON), status
  input_tokens, output_tokens, duration            ← 用于成本归因

AgentDecision
  id, runId, action, status, payload(JSON), createdAt
```

`AgentRun.steps` / `approvals` / `toolCalls` 用 `cascade="all, delete-orphan"`，删除运行即清空其子记录。

### 7.3 知识库数据契约

```text
DocumentChunk
  id, userId, sourceName, sourceType, chunkIndex, content
  embedding: Vector(1024)
  createdAt
  索引： (userId, sourceName)  (sourceName)  +  HNSW(embedding vector_cosine_ops)

KnowledgeDoc
  id, userId, sourceName, sourceType, content, createdAt
  唯一约束： (userId, sourceName)                   ← 同一用户同一来源只保留一份
```

### 7.4 向量存储的三个硬约束

1. **向量列必须是 pgvector 类型**，由迁移 `0004` 用 `Vector(1024)` 建立并配 `USING hnsw (embedding vector_cosine_ops) WITH (m=16, ef_construction=64)`；不允许用 `TEXT` 存 JSON 数组冒充向量列。
2. **不需要的列不要取**：Top-K 查询只 SELECT 命中需要的字段，不把 1024 维向量搬回应用层。旧实现把最多 1000 行向量取回 Python 再算余弦，是延迟与召回双重恶化的根因。
3. **用 `SET LOCAL` 而不是 `SET`**：`hnsw.ef_search` 只对当前事务生效，不污染连接池里后续的其他查询。

### 7.5 迁移策略

| 版本 | 内容 |
|---|---|
| `0001_initial` | 业务主表与约束 |
| `0002_garden` | 花园玩法表 |
| `0003_garden_matured` | 成熟阶段字段 |
| `0004_rag_vector_index` | pgvector 扩展、`Vector(1024)` 列、HNSW 索引 |

约束：迁移只向前演进，每版都能在空库上从零跑通；schema 变更必须配套迁移文件，不接受手工 `ALTER` 后不落迁移。已知坑：迁移系统只保证「版本号前进」，不保证「物理状态符合预期」——手工删过索引后 `alembic upgrade head` 会直接跳过已标记应用的版本，必须显式重建并用 `pg_indexes` 复查。

---

## 8. RAG 摄取、检索与精排

### 8.1 摄取契约

```text
upload → 格式解析 → 分块 → embedding → DocumentChunk 落库
```

- 分块策略：`split_text(text, chunk_size=500, overlap=50)` 为先按空行分段、再固定长度切分，并在句末标点处回退断开；`split_markdown(text, max_chunk_size=800)` 按 `##` 标题语义分片，超长段落内部再切分并保留标题行。
- 重叠切分有一个必须处理的边界：切到文本末尾时若剩余尾巴短于 `overlap`，`advance` 会退化为 1，导致「每次前进一个字」的重复分片，因此末尾必须显式 `break`。
- embedding 走模型池的 EMBEDDING 档，不计入用户 token 配额。

### 8.2 检索契约

```python
search_similar_chunks(query_embedding, top_k=5, source_filter=None, user_id=None) -> list[DocChunk]
```

- 过滤条件：`embedding IS NOT NULL`，可选 `userId`、`sourceName`。
- 排序：`ORDER BY embedding <=> query`（余弦距离算子）。
- 事务内先执行 `SET LOCAL hnsw.ef_search = 100`。
- 返回值 `DocChunk` 不含 embedding：`id / sourceName / sourceType / chunkIndex / content / createdAt`。

`search_similar_chunks_scan`（全量搬运 + Python 余弦）保留在同一文件里，只用于评测基线对比，生产代码不再调用。

### 8.3 精排与拒答

```text
召回 Top-20 → 本地余弦重排 → Top-5 → 阈值判断 → 拼 Prompt
```

- 精排放在应用层而不是数据库：将来要加来源权重、时间衰减或换 Cross-Encoder，只改这一层，不动召回 SQL。
- Top-20 条 1024 维向量在 CPU 上重算余弦的耗时可忽略（实测 < 0.2ms）。
- 精排异常时回退到纯向量排序，并把 `score` 置 0 标记「无重排分数」，不阻断回答。
- 拒答：Top-1 相似度低于 **0.45** 时走拒答话术，明确区分「知识库没查到」和「按通用知识补充」。

### 8.4 `ef_search` 的决策依据

HNSW 是近似索引，`ef_search` 决定搜索时探索多少候选。基准用 `SET enable_indexscan = off` 强制顺序扫描拿精确 Top-K，再逐档对比（9885 块语料 / 40 条有答案问题）：

| `ef_search` | Hit@5 | Recall@20 | P50 |
|---|---|---|---|
| 精确全扫（上限） | 0.925 | 0.950 | 24.8ms |
| 1 | 0.450 | 0.450 | 0.7ms |
| 10 | 0.800 | 0.825 | 0.8ms |
| 40（pgvector 默认） | 0.850 | 0.875 | 1.1ms |
| **100（采用）** | **0.900** | **0.925** | **1.4ms** |
| 200 | 0.900 | 0.925 | 2.0ms |
| 400 | 0.925 | 0.950 | 2.8ms |

取 100 的理由：默认值 40 相对精确检索丢 7.5pp 召回，调到 100 补回 5pp，代价只有 0.3ms；再往上到 400 相对 100 只多命中 1 条问题（n=40），样本量下不足以证明这不是噪声，所以不基于单条差异继续调参。`ef=200` 与 `100` 完全同分，说明曲线已进入平台区。

一个必须记住的实验陷阱：小表（不到一万行）的代价模型会让规划器在 `ef_search` 较小时**直接放弃 HNSW 改走 Seq Scan**，此时量到的是全表扫描而不是索引表现。参数实验必须用 `EXPLAIN ANALYZE` 确认执行计划，否则量到的不是你想量的东西。

### 8.5 评测结果与口径

语料：Python-100-Days 中文资料 126 篇 Markdown → 9885 个 chunk；向量为 1024 维；评测问题 50 条（40 有答案 + 10 无答案，`SEED=42` 固定）。

| 路径 | Hit@5 | Recall@20 | MRR@5 | P50 | P95 |
|---|---|---|---|---|---|
| `scan`（旧：全量搬运 + `LIMIT 1000`） | 0.075 | 0.075 | 0.075 | 271.1ms | 300.0ms |
| `sql` 无索引（精确全扫） | 0.925 | 0.950 | 0.7746 | 33.2ms | 43.7ms |
| `sql` + HNSW `ef_search=100`（生产） | 0.900 | 0.925 | 0.7621 | 6.7ms | 7.9ms |

口径必须讲清楚：

- 旧实现的 7.5% 是**召回缺口**而不是「排得不好」：候选集被 `LIMIT 1000` 限死在最新录入的 1000 块，而语料有 9885 块，理论上限约 10%，实测值基本贴着天花板。这是正确性缺陷，不是调优空间。
- 端到端对比中真正属于检索优化的收益是「引用率 4/10 → 9/10」和「可答问题答『没找到』7/10 → 0/10」；TTFT 与整段耗时的差异主要由模型侧波动造成，检索 6.7ms 在整段十几秒的耗时里占比不到 0.2%，不能算成优化收益。
- 数据集局限：`hit@5` 与 `recall@20` 数值经常一致，说明 gold 块大多排在前 5，题目偏「单块可答」，缺少跨块归纳的难题。这套数字衡量的是「检索链路有没有坏」，不是难度上限。
- 拒答阈值的数据依据：有答案问题 Top-1 相似度最低 0.5012，无答案问题最高 0.4038，两段分布有清晰间隔，中间取 0.45 可区分。

完整过程、命令、踩坑记录见 `scripts/rag_eval/RAG_EVAL.md`。

---

## 9. Agent Runtime 与工具调用

### 9.1 运行状态机

```text
                 ┌──────────── cancelled
                 │
queued ──► running ──► awaiting_approval ──► completed
                 │            │
                 │            └────────────► rejected
                 └────────────► failed
```

| 状态 | 进入条件 | 允许的后续 |
|---|---|---|
| `queued` | 运行已创建、尚未开始 | `running` / `cancelled` |
| `running` | 正在执行某个 Step | `awaiting_approval` / `completed` / `failed` / `cancelled` |
| `awaiting_approval` | 产出需要人工确认的 action | `completed` / `rejected` |
| `completed` | 四步执行完且 summary 已生成 | 终态 |
| `failed` | 任一步骤抛异常 | 终态（保留已完成步骤） |
| `cancelled` | 用户主动取消 | 终态 |
| `rejected` | 用户拒绝审批项 | 终态 |

### 9.2 步骤落表

| Step | kind | input | output |
|---|---|---|---|
| 1 | `observe` | `{userId}` | 打卡/计划/任务/专注/记忆统计摘要 |
| 2 | `analyze` | 精简后的上下文 + 记忆摘要 | `{status, findings[], actions[]}` |
| 3 | `plan` | analysis 结果 | `{findingCount, actionCount}` |
| 4 | `execute` | action 列表 | 每条 action 的执行结果 |

`(runId, stepNumber)` 唯一约束保证顺序不重复；`Step.status` 取 `running / completed / failed`，`Step.error` 记录失败原因。

### 9.3 工具注册表（14 个）

| 分类 | 工具 | 说明 |
|---|---|---|
| study | `getStudyStats` | 打卡天数、连续打卡、计划进度 |
| study | `getMyPlans` | 计划列表与进度，可按 active/completed 过滤 |
| study | `getRecentCheckins` | 最近打卡记录，默认 7 天、上限 30 天 |
| study | `getMyMemories` | 长期记忆查询，可传 query 走语义搜索 |
| study | `createPlan` | 创建学习计划 |
| todo | `getMyTodos` | 今日待办清单，未完成在前 |
| todo | `createTodo` | 新增今日待办 |
| todo | `updateTodo` | 勾选完成/取消，或改标题 |
| todo | `deleteTodo` | 删除待办 |
| rag | `searchKnowledgeBase` | 仅检索当前用户已上传的文档 |
| agent | `breakdownPlanTasks` | 把计划拆成平铺的可执行任务 |
| agent | `getPlanTasks` | 查询某计划全部任务与进度 |
| agent | `updateTaskStatus` | 更新任务状态 pending/in_progress/done/skipped |
| agent | `getTodayTasks` | 今日应完成任务清单 |

### 9.4 工具契约与安全

- 每个工具都是 `create_*_tools(user_id)` 的闭包产物，`user_id` 在创建时绑定，**不接受模型传入的用户标识**。
- 模型只拿到 JSON Schema，拿不到数据库连接和凭据。
- 工具返回统一为结构化字典：成功含 `success: true` 与载荷，失败含 `success: false` 与 `error`。
- 工具内部异常由 `safe_execute` 兜住，**不允许中断整次聊天请求**。
- 涉及已有对象写入的工具（`updateTodo` / `deleteTodo` / `updateTaskStatus` / `breakdownPlanTasks` / `getPlanTasks`）必须校验对象归属，模型给的 ID 不等于有权限。
- 工具循环有界：对话链路最多 4 轮，超出后强制要求模型产出最终文本。

### 9.5 降级

| 故障 | 行为 |
|---|---|
| 模型 JSON 解析失败 | 重试一次，仍失败则走 `fallback_analysis` 规则兜底 |
| 模型池全档不可用 | `fallback_analysis` 依阈值产出保底建议，`AgentRun` 仍写 `completed` |
| 单条 action 执行失败 | 该条 `AgentDecision` 记失败原因，其余 action 继续 |
| 通知重复 | 同类型当日只发一条 |
| 工具未知 | 返回 `{"success": false, "error": "未知工具: <name>"}` |

---

## 10. 模型池与容错降级

### 10.1 分档与链条

| 档位 | 用途 | 链长 |
|---|---|---|
| HIGH | Agent 分析、文档工作室、后台规划 | 8 |
| LOW | 聊天室回复、标题生成、记忆抽取、计划拆分 | 5 |
| EMBEDDING | 知识库与记忆向量化 | 2 |

每个 `ModelEntry` 记录 `modelName / displayName / provider / modelType / tier / thinking / freeQuotaEnd`。新增供应商只改 `PROVIDER_CONFIG` 和对应链条，调用方零改动。

### 10.2 错误分类

| 错误 | 判定 | 处理 |
|---|---|---|
| 403 / 额度耗尽（`AllocationQuota.FreeTierOnly`、`InsufficientBalance`） | 本进程生命周期内的确定性失败 | 加入 `_exhausted_models`，本进程不再尝试 |
| 429 / rate limit | 临时状态 | `_rate_limited_until[model] = now + 60s`，到期自动恢复 |
| 其他异常 | 不确定 | 记日志并切下一个模型，不静默吞掉 |

**这两类必须严格区分**：混为一谈会出现两种反向错误——把临时限流当成永久损坏（此后再也不会切回该模型），或把永久耗尽当成临时问题（每次都白白重试一次失败调用）。

### 10.3 冷却与恢复

- 冷却窗口默认 60 秒（`cooldown_ms=60_000`）。
- 可用性判定 `is_model_available(name)`：在耗尽集合中直接返回 False；在冷却字典中且未到期返回 False；已到期则从字典移除并返回 True。
- `_chain_for(tier)` 与 `_embedding_chain()` 每次调用都重新过滤可用模型，并跳过未配置 API Key 的供应商。

### 10.4 SDK 重试策略

OpenAI 客户端以 `max_retries=0` 创建。理由：SDK 内部重试会把 429 拖成十几秒的等待，而切流决策权在模型池手里。关闭 SDK 重试才能保证「失败 → 立即切下一个 → 用户零感知」的时序。

### 10.5 并发与线程安全

`_exhausted_models`（set）与 `_rate_limited_until`（dict）由模块级 `threading.Lock` 保护。同一次请求内多个工具调用可能并发触发模型调用，锁保证标记与查询不会读到中间状态。

### 10.6 记账

每次成功调用后写 `TokenUsage`，记录 `surface`（chat / title / memory / agent / studio）、`userId`、`tier`、`model`、输入输出 token。交互式面（agent / studio / 聊天室）在调用前执行 `assert_interactive_usage_allowed`，只剩 0 时抛 `UsageLimitError`；embedding 不计入用户配额。用量数据是成本归因的依据，不是供应商账单的替代品。

### 10.7 边界

模型池状态是**进程内**的：多实例部署时，A 实例标记耗尽的模型在 B 实例仍然会被尝试；进程重启后耗尽状态清空，已耗尽的模型会被再试一次并立即失败。这是当前的已知边界，见 §17 与 §18。

---

## 11. Realtime 长连接治理

### 11.1 消息协议

所有消息都是 `{ "type": ..., ...payload }` 的类型化 JSON。单房间模式，没有 roomId。

服务端 → 客户端：

| type | 载荷 | 触发时机 |
|---|---|---|
| `ready` | `user{id,name,image}` | 连接注册成功 |
| `message` | `message{id,userId,userName,image,role,content,createdAt}` | 有人发言或 AI 回复落库 |
| `ai:start` | `{role}` | AI 开始生成 |
| `ai:delta` | `{delta}` | 流式增量 |
| `ai:done` | `{message}` | AI 回复完成 |
| `presence` | `{online}` | 有人加入或离开 |
| `pong` | — | 响应客户端 ping |
| `error` | `{code, reason}` | 长度超限、限流、非法消息 |

客户端 → 服务端：`message`（带 `clientId`）、`ping`。

`createdAt` 统一用 ISO 8601 UTC 带 `Z`，与前端 `toISOString()` 对齐。

### 11.2 治理五件套

| 机制 | 参数 | 解决的问题 |
|---|---|---|
| 握手鉴权 | token 来自 query 或 Cookie，失败 `close 1008` | 匿名连接占资源 |
| 心跳 | 每 30s 扫描，`last_seen` 超 60s（2×）主动断 | 浏览器断电/关页面不发 close，半开连接会泄漏几十分钟 |
| 滑动窗口限流 | `RATE_LIMIT_WINDOW_MS=60_000`，`RATE_LIMIT_MAX=30` | 脚本一分钟刷上千条，广播把所有在线用户卡住 |
| clientId 去重 | `MAX_SEEN_CLIENT_IDS=200` 的环 | 用户点两下、网络重传导致重复落库与重复 AI 回复 |
| presence 广播 | `{online: n}` | 连接数变化及时同步，也是治理效果的可视化验证 |

心跳是**全局独立 asyncio task**，不依赖客户端是否会发 pong，因此消息长度上限（`MAX_MESSAGE_LENGTH=2000`）与限流检查都在服务端强制执行。

### 11.3 已知边界

连接表、限流窗口、去重环都在进程内；单实例部署没有问题，多实例时需要外置广播（见 §18）。

---

## 12. 安全与用量治理

### 12.1 密码与会话

```text
scrypt(password, salt, N=16384, r=16, p=1, dklen=64)
存储格式： "<salt_hex>:<hash_hex>"
校验：比较用 hmac.compare_digest（常数时间），格式非法直接判失败
```

选择 scrypt 的额外原因：需要与前端的既有认证方案互通密码哈希格式。`N=16384` 是安全与算力的折中——单次哈希约 100–200ms，足以抵抗彩虹表，又不会让登录卡顿。显式设置 `maxmem = 128 × N × r × 2`，否则 Python 的 `hashlib.scrypt` 会因为默认内存上限不足直接抛错。

会话用 HS256 JWT，7 天过期，读取顺序为 Cookie → `Authorization: Bearer`：

| 场景 | 使用方式 |
|---|---|
| 浏览器同域前端 | Cookie 自动携带，前端 52 处 fetch 不需要额外设置 header |
| 第三方客户端 / 脚本 | `Authorization: Bearer <token>` |

Token 解码失败、用户不存在、密码不匹配一律返回 401，不区分具体原因，避免账号探测。

### 12.2 用户隔离

- 所有业务查询必须带 `userId`。
- 所有 AI 工具在创建时绑定 `userId` 闭包。
- 模型可见的上下文里不包含其他用户的数据；跨用户读取在工具层就被拒绝。
- 删除用户依赖外键 `CASCADE` 级联清理业务数据、消息、记忆、文档块与向量，不需要额外的补偿任务。

### 12.3 Prompt 边界

- 系统提示词、工具白名单、用户归属属于系统侧，不接受用户文本覆盖。
- 上下文窗口固定为最近 20 轮（40 条），更早的内容不在模型可见范围内；提示词中明确要求「无法看到较早内容时请用户补充，不要凭空编造历史对话」。
- 长期记忆注入按 `importance` 排序并受条数限制，不能无限扩张。
- 检索结果以 `[参考N]（来源: xxx）` 形式注入，来源名保留，便于回答里给出引用。

### 12.4 用量限额

`AI_TOKEN_LIMIT` 默认 200000，按自然日统计（`0` 表示不限）。检查点在交互式入口之前，超限抛出 `UsageLimitError` 并返回「精力条耗尽」类的友好提示，而不是 500。embedding 调用不计入用户配额。

### 12.5 上线前必须修改的项

仓库中的默认值只适用于本地开发，公网部署前必须修改：

1. `JWT_SECRET` 不能使用默认值，改为强随机字符串。
2. 数据库密码不能使用默认 `postgres`。
3. `AI_TOKEN_LIMIT` 按自己账户的真实额度重设。
4. nginx 前面加 HTTPS，Cookie 补 `Secure`、`HttpOnly`、`SameSite=Lax`。

---

## 13. 测试与评估

### 13.1 三层结构

| 层 | 位置 | 覆盖内容 |
|---|---|---|
| 单元 | `tests/`（5 个模块） | 分块边界、计划同步解析、密码与哈希、AI 契约常量、WS @AI 解析 |
| 评测 | `scripts/rag_eval/` | 检索质量、索引参数扫描、端到端行为 |
| 手工冒烟 | `scripts/test_*.py` | 鉴权、业务、聊天、Agent、模型池、WS 的本地验证脚本 |

单元测试只覆盖**确定性部分**：纯函数、契约常量、解析逻辑。不访问真实模型，不依赖数据库。

### 13.2 命令

```bash
python -m compileall -q app scripts alembic
python -m unittest discover -s tests -v
cd frontend && npm run typecheck && npm run lint && npm run build
```

### 13.3 评测纪律

调整检索行为时必须记录：

1. 语料规模与 chunk 数；
2. 问题集及是否含无答案问题；
3. 索引与 `ef_search` 参数；
4. 实际使用的指标（Hit / Recall / MRR）；
5. 延迟分布，以及口径是「纯检索」还是「端到端」；
6. 已知局限与本轮测量错误。

不允许把两次口径不同的测量直接相减得出结论。评测中曾经出现过一次归因错误（把裸 SQL 取回耗时与 ORM 全链路耗时相减，推断「瓶颈在向量传输」），该结论已在 `RAG_EVAL.md` 中显式撤销并标记为待验证。

### 13.4 需求追踪

```text
spec.md 需求（R-xxx-nn）
  → plan.md 设计条目
  → tasks.md 任务（T-xxx-nn）
  → tests/ 或 scripts/rag_eval/ 的验收方式
```

禁止出现「实现了但没有验收方式」的 P0 需求。

### 13.5 未覆盖

- 没有数据库集成测试套件；
- 没有自动化浏览器端到端测试；
- 没有针对每一档模型的 Provider Mock 契约测试；
- 没有部署流水线。

---

## 14. 部署与运行

### 14.1 Compose 编排

```text
db       pgvector/pgvector:pg16      healthcheck: pg_isready（retries 12）
app      build .                     depends_on: db(service_healthy)
web      build ./frontend            depends_on: app
nginx    nginx:alpine  :80           depends_on: app, web
```

### 14.2 启动顺序硬约束

应用容器入口先执行 `alembic upgrade head` 再启动 uvicorn。配合 `depends_on: db.condition: service_healthy`（用 `pg_isready` 探活、最多重试 12 次），保证新版本上线时不会出现「代码是 0004、库还在 0003」的窗口。

### 14.3 Nginx 关键配置

| 位置 | 关键项 | 原因 |
|---|---|---|
| `/ws` | `Upgrade` / `Connection: upgrade`，`proxy_read_timeout 3600s` | 长连接不能被默认超时切断 |
| `/api/` | `proxy_buffering off`，`proxy_read_timeout 300s` | AI 流式响应不能被缓冲；Agent 多轮工具调用会让首字节前空档很长 |
| `/` | `proxy_set_header Host $http_host` | 非标准端口时 Next.js Server Actions 会校验 `x-forwarded-host` 与 origin 一致，`$host` 会丢端口导致 500 |
| 全局 | `client_max_body_size 20m` | 知识库上传 docx / pdf |

### 14.4 健康检查与回归

```bash
curl -s http://127.0.0.1/health
python -m unittest discover -s tests -v
```

### 14.5 回滚

- 应用与前端可独立回滚镜像；
- 数据库迁移需要先确认目标版本可降级，或在 forward 迁移中保证向后兼容；
- 回滚前确认没有正在执行的 Agent 运行；
- 回滚后复查 `pg_indexes` 确认索引物理存在。

---

## 15. 工程规范

### 15.1 提交前缀

```text
feat(ai):     feat(rag):    feat(agent):   feat(web):
fix(ws):      fix(api):     fix(db):
docs(spec):   docs(adr):
test(rag):
chore(repo):  chore(ci):
```

### 15.2 变更顺序

1. 先改 `specs/<capability>/spec.md`（对外行为有变化时）；
2. 再改 `plan.md`（技术路径有变化时）；
3. 改实现；
4. 补测试或可复现的验证命令；
5. 检索行为有变化时更新 `scripts/rag_eval/` 证据；
6. 本地跑 `compileall` + `unittest` + 前端 `typecheck/lint`；
7. 提交并观察 CI。

### 15.3 代码边界

- Router 不写业务规则；
- Service 不处理 HTTP 语义；
- AI 组件不复用请求线程 Session；
- 工具不得信任模型传入的用户标识；
- 前端不直连数据库，不保存服务端密钥；
- 规格里不写未实现的能力。

### 15.4 CI

GitHub Actions 两个 job：

```text
backend : pip install -r requirements.txt
          → python -m compileall -q app scripts alembic
          → python -m unittest discover -s tests -v
frontend: npm ci → npm run typecheck → npm run lint
```

---

## 16. 交付里程碑

### Phase A · 契约

- 定义 AI 请求/响应契约、WS 消息类型、Agent 运行状态与步骤类型；
- 建立错误语义与降级约定；
- 建立数据模型与初始迁移。

### Phase B · 学习闭环

- 计划 / 任务 / 待办 / 打卡 / 专注 / 统计；
- 计划文档与任务同步（`source_hash` 幂等）；
- 花园玩法与延迟奖励。

### Phase C · AI 对话

- 模型池分档与 403 / 429 区分；
- 上下文截断、记忆注入、工具注册表；
- 有界工具循环与流式输出；
- Token 记账与每日限额。

### Phase D · RAG

- 分块策略与边界处理；
- pgvector 迁移与 HNSW 索引；
- 数据库侧 Top-K 检索（替换全量搬运实现）；
- 精排、拒答阈值与来源引用；
- 评测脚本与 `RAG_EVAL.md`。

### Phase E · Agent Runtime

- 四步状态机与四张落表；
- 14 个用户域工具；
- 审批与决策；
- 规则兜底 `fallback_analysis`；
- 每日巡检入口与定时调度。

### Phase F · Realtime

- WS 握手与房间注册；
- 心跳、限流、去重、presence；
- `@AI` 解析与异步回复广播。

### Phase G · 交付

- Docker Compose 四服务；
- Nginx 同域与流式配置；
- CI；
- `README` / `DEV_SPEC` / `specs` / `docs`；
- 部署、排障与回滚说明。

---

## 17. 已知边界

1. 模型池的耗尽集合与冷却字典是进程内状态，多实例不共享，重启后清空。
2. WebSocket 连接表、限流窗口、去重环同为进程内对象，当前只支持单实例广播。
3. 签到与专注的幂等依赖应用层「先查后写」，数据库层没有唯一约束兜底。
4. 长期记忆的默认排序不完全依赖向量近邻，向量能力只在显式查询路径上使用。
5. 生产检索路径取回整行记录后再映射为 `DocChunk`，未做列裁剪；更彻底的列投影仍是待办项。
6. 评测集以「单块可答」问题为主，缺少需要跨块归纳的难题，指标反映的是链路健康度而非难度上限。
7. 端到端评测只有 10 条可答 + 3 条无答案问题，且观察到过一次空响应，样本量不足以支撑小数点后的比较。
8. 没有数据库集成测试、浏览器端到端测试与 Provider Mock 契约测试。
9. 没有对外暴露的监控指标与告警；定位问题依赖日志与数据表状态。
10. 前端 `typecheck` / `lint` / `build` 通过，但没有视觉回归与可访问性测试。

---

## 18. 演进路线

### 18.1 状态外置

- 把模型池的耗尽/冷却状态迁到共享存储，多实例下冷却互相可见；
- WebSocket 广播改为跨节点发布订阅；
- Agent 运行状态支持断点续跑。

### 18.2 数据完整性

- 为签到、专注、任务同步补数据库唯一约束，把幂等从应用层下沉到 schema；
- 为 `PlanTask.source_hash` 增加唯一索引；
- 迁移执行后自动校验索引物理存在。

### 18.3 检索增强

- 检索 SQL 做列裁剪，只取必要字段；
- 精排层接入 Cross-Encoder，替换本地余弦；
- 引入 Query Rewrite 与来源权重；
- 扩充评测集，加入跨块归纳类难题与更大规模语料；
- 补三段对照实验，把「取回量 / 解析 / 计算」三部分耗时分离测量。

### 18.4 可观测性

- 引入 OpenTelemetry，覆盖 HTTP、WS、模型调用与检索；
- 输出关键指标：模型错误率、切换次数、检索延迟、Agent 成功率；
- 建立告警阈值与运行手册。

### 18.5 部署与运维

- 补部署流水线（构建 → 测试 → 发布）；
- 增加灰度与回滚脚本；
- 数据备份与恢复演练。

### 18.6 规模

- 10 万用户内维持 pgvector 单库 + 单机扩容；
- 10 万–100 万用户：向量迁独立集群、聊天与通知走消息队列、读多写少的统计走缓存；
- 100 万以上：按 `user_id` 分库分表，模型池与 WS 广播全部外置。

---

## 19. 术语表

| 术语 | 定义 |
|---|---|
| OAPE | Observe → Analyze → Plan → Execute，Agent Runtime 的四步循环 |
| AgentRun | 一次 Agent 运行的持久化记录 |
| AgentStep | 运行中的单个步骤，`(runId, stepNumber)` 唯一 |
| AgentApproval | 需要人工确认的动作记录 |
| AgentDecision | 单条 action 的执行结果记录 |
| ModelEntry | 模型池中的一条模型定义 |
| tier | 模型档位：`high` / `low` / `embedding` |
| exhausted | 额度耗尽，本进程内不再尝试 |
| rate limited | 临时限流，冷却 60 秒后恢复 |
| DocChunk | 检索返回的文档块，不含 embedding |
| ef_search | HNSW 搜索时探索的候选数量 |
| RRF | Reciprocal Rank Fusion，按名次而非分数融合多路召回 |
| 拒答阈值 | Top-1 相似度低于该值时明确说明知识库无答案 |
| source_hash | 计划拆解输入的哈希，用于幂等 |
| presence | 在线人数的广播消息 |
| clientId | 客户端消息去重标识 |
