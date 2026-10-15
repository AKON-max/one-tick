# Tasks: RAG Retrieval

## Phase 1 · 数据与迁移

- [x] T-RAG-00 定义 `Document` / `DocumentChunk` / `KnowledgeDoc` 模型与索引
- [x] T-RAG-01 `DocumentChunk.userId` 外键 + `ON DELETE CASCADE`
- [x] T-RAG-05 `KnowledgeDoc` 对 `(userId, sourceName)` 建唯一约束
- [x] T-RAG-16 迁移 `0004_rag_vector_index`：pgvector 扩展 + `Vector(1024)` + HNSW(m=16, ef_construction=64)

## Phase 2 · 摄取

- [x] T-RAG-02 `split_text`：分段 → 限长 → 句末标点优先回退
- [x] T-RAG-03 末尾 `break` 保护，避免重叠切分退化为逐字前进
- [x] T-RAG-17 `split_markdown`：`##` 语义分片，超长段落保留标题行
- [x] T-RAG-04 向量化走 EMBEDDING 档与自动切换
- [x] T-RAG-18 上传入口按用户归属写入

## Phase 3 · 检索

- [x] T-RAG-06 `_filters`：排除空向量，支持 `userId` / `sourceName` 过滤
- [x] T-RAG-07 `SET LOCAL hnsw.ef_search = 100`
- [x] T-RAG-08 返回值不含 embedding（`DocChunk` 契约）
- [x] T-RAG-09 召回 Top-20 → 精排 Top-5
- [x] T-RAG-10 精排失败回退真实顺序，`score` 置 0
- [x] T-RAG-11 拒答阈值 0.45 与两段分布依据
- [x] T-RAG-12 `searchKnowledgeBase` 工具：`found` / `count` / `searchedChunks` / 结果列表
- [x] T-RAG-19 `format_knowledge_for_prompt` 保留来源名

## Phase 4 · 评测

- [x] T-RAG-13 评测用户隔离与 `teardown.py` 清理
- [x] T-RAG-14 `eval_rag.py` 双路径对比与指标输出
- [x] T-RAG-20 `sweep_ef.py` 扫描曲线（`enable_seqscan = off`）
- [x] T-RAG-15 `eval_e2e.py` 端到端行为验证（含无答案问题）
- [x] T-RAG-21 `RAG_EVAL.md` 记录方法论、原始数据、踩坑与撤销的归因
- [x] T-RAG-22 `questions.jsonl` 固定 `SEED=42`，40 有答案 + 10 无答案

## Phase 5 · 验证

- [x] T-TEST-RAG-01 `tests/test_chunking.py` 四个分块边界用例
- [x] T-TEST-RAG-02 编译与单测进入 CI

## Follow-up

- [ ] T-PROD-RAG-01 检索 SQL 列裁剪，去掉不必要的字段返回
- [ ] T-PROD-RAG-02 精排层接入 Cross-Encoder
- [ ] T-PROD-RAG-03 补三段对照实验（裸取回 / 仅解析 / 解析+计算），分离传输与计算耗时
- [ ] T-PROD-RAG-04 扩充评测集，加入跨块归纳类难题
- [ ] T-PROD-RAG-05 语料规模上台阶时评估独立向量存储

## Traceability

| 需求 | 任务 | 验证 |
|---|---|---|
| R-RAG-01 | T-RAG-18 | 越权用例 |
| R-RAG-02 | T-RAG-02 | `test_chunking.py` |
| R-RAG-03 | T-RAG-03 | `test_chunking.py` |
| R-RAG-04 | T-RAG-17 | `test_chunking.py` |
| R-RAG-05 | T-RAG-04 | 模型池验证 |
| R-RAG-06 | T-RAG-05 | schema 约束 |
| R-RAG-07 | T-RAG-01 | CASCADE 用例 |
| R-RAG-08 | T-RAG-06 | 评测 |
| R-RAG-09 | T-RAG-07 | SQL 检查 |
| R-RAG-10 | T-RAG-06 | 检索用例 |
| R-RAG-11 | T-RAG-08 | 契约检查 |
| R-RAG-12 | T-RAG-09 | 契约常量 |
| R-RAG-13 | T-RAG-10 | 回退用例 |
| R-RAG-14 | T-RAG-11 | 端到端评测 |
| R-RAG-15 | T-RAG-19 | Prompt 格式检查 |
| R-RAG-16 | T-RAG-12 | 工具契约 |
| R-RAG-17 | T-RAG-21 | 文档评审 |
| R-RAG-18 | T-RAG-14 | `eval_rag.py` |
| R-RAG-19 | T-RAG-15 | `eval_e2e.py` |
