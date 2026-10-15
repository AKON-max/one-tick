# Specifications

本目录是 One-Tick 的行为契约与实现规格，分成两层：

```text
specs/
├── DEV_SPEC.md              项目级设计规格：目标、原则、选型、架构、数据契约、参数决策、测试与演进
├── README.md                本文件：目录约定与状态索引
├── _template/               新建能力规格时的骨架
└── <nnn>-<capability>/
    ├── spec.md              对外可观察行为、状态机、失败语义、验收标准
    ├── plan.md              实现路径、组件边界、风险与回滚
    └── tasks.md             工作拆分与需求追溯
```

## 当前能力

| ID | 能力 | 状态 | 备注 |
|---|---|---|---|
| 001 | AI Chat Orchestration | implemented | 上下文 20 轮 / 40 条；工具循环 ≤ 4 轮 |
| 002 | RAG Retrieval | implemented | 生产配置 Hit@5 0.900 / Recall@20 0.925；检索列裁剪仍待办 |
| 003 | Agent Runtime and Approval | implemented | 四步落表；进程内无可续跑队列 |
| 004 | Realtime Chat | implemented | 单实例进程内连接表，已显式声明边界 |

## 约定

1. 一个 spec 只覆盖一个对外可观察的能力。
2. 需求 ID 稳定不复用：`R-<域>-<序号>`，删除的需求保留编号并标记 superseded。
3. 每条 P0 需求必须在 `tasks.md` 里有对应任务、在 `spec.md` 验收标准里有对应方式。
4. 验收方式必须是一条命令、一个测试或一段可复现的手工步骤，不接受「人工确认看起来对」。
5. 指标必须带语料规模、样本量、索引参数与运行口径；口径不同的两次测量不能直接相减。
6. 已知边界保留在 `spec.md` 里，直到它被真正移除。
7. 对外行为变化时，spec 与代码在同一个变更里更新。
