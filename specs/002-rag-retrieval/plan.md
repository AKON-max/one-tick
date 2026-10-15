# Technical Plan: RAG Retrieval

| 字段 | 值 |
|---|---|
| Spec | `002-rag-retrieval` |
| Status | implemented |
| Components | `routers/knowledge.py`、`routers/documents.py`、`ai/rag/{chunk,client,retriever,search}.py`、`ai/tools/rag_tools.py`、`models/knowledge.py`、`alembic/versions/0004_rag_vector_index.py` |
| State | 向量与业务事实同库；没有独立向量数据库 |
| Rollback | 代码可回退；索引需显式重建并复查 `pg_indexes`，不能只依赖 `alembic upgrade head` |

## 1. 实现路径

```text
摄取：上传 → 解析 → split_text / split_markdown → embedding_with_fallback
      → DocumentChunk(userId, sourceName, chunkIndex, content, embedding)

检索：query → embedding → SET LOCAL hnsw.ef_search = 100
      → ORDER BY embedding <=> query LIMIT 20
      → 本地余弦精排 Top-5 → 阈值判断 → 带来源名拼 Prompt
```

## 2. 组件边界

- `chunk.py` 只做文本切分，不接触数据库与模型。
- `client.py` 只负责向量化，通过模型池的 EMBEDDING 档。
- `retriever.py` 只负责数据库侧近邻查询，不做打分重排。
- `search.py` 负责编排召回、精排、拒答与 Prompt 格式化。
- `rag_tools.py` 把检索包成用户域工具，不参与业务写入。

四层各自可单独测试；`retriever.py` 里的 `search_similar_chunks_scan` 只保留给评测做基线对比，生产不调用。

## 3. 用户隔离与清理

- `DocumentChunk.userId` 外键 `ON DELETE CASCADE`：删用户即清空其文档块与向量。
- `KnowledgeDoc` 对 `(userId, sourceName)` 建唯一约束，避免同一来源重复入库。
- `_filters()` 中 `user_id` 为可选参数，但所有对外入口（工具、路由）都必须传。

## 4. 分块

| 策略 | 参数 | 用途 |
|---|---|---|
| `split_text` | `chunk_size=500`、`overlap=50` | 纯文本、PDF 解析结果 |
| `split_markdown` | `max_chunk_size=800` | 结构良好的 Markdown |

两个边界必须处理：

1. 长段落切分时优先在句末标点（。？！.?! 中文优先）回退断开，避免把句子劈开。
2. 切到末尾时剩余尾巴长度可能小于 `overlap`，此时 `advance = len(chunk) - overlap ≤ 0`；若不做显式终止就会把 `advance` 强制成 1，退化成「每次前进 1 个字」的重复分片。因此循环内必须先判断 `end >= len(trimmed)` 直接 `break`。

## 5. 向量化

`embedding_with_fallback()` 走 EMBEDDING 档，链条为 `text-embedding-v4` → `text-embedding-v2`。embedding 不计入用户 token 配额，因为它是系统侧成本（用户看到的是检索质量，不是向量账单）。

## 6. 数据库侧检索

```python
distance = DocumentChunk.embedding.cosine_distance(query_embedding)
stmt = select(DocumentChunk).where(*_filters(source_filter, user_id)).order_by(distance).limit(top_k)
with SessionLocal() as db:
    db.execute(text(f"SET LOCAL hnsw.ef_search = {HNSW_EF_SEARCH}"))
    rows = db.execute(stmt).scalars().all()
```

三个必须坚持的点：

1. Top-K 在数据库完成，不走「取回全部再在 Python 算」。
2. `SET LOCAL` 而非 `SET`：只作用于当前事务，不污染连接池中该连接的后续查询。
3. 用 `cosine_distance` 而不是手动算点积，让规划器有机会使用 HNSW 索引。

## 7. 精排与拒答

- 召回 Top-20 后在本层重算余弦并排序取 Top-5。放在应用层的理由是：将来加来源权重、时间衰减或换 Cross-Encoder 只改这里，不动召回 SQL；20 条 1024 维向量在 CPU 上耗时可忽略。
- 精排异常：捕获后回退原始顺序，`score` 置 0，日志记录原因。
- 拒答：Top-1 相似度 < 0.45 时回答「知识库中未找到相关内容」，并明确说明接下来是通用知识补充。

阈值的数据依据：有答案问题 Top-1 相似度最低 0.5012，无答案问题最高 0.4038，中间取 0.45 有清晰间隔。

## 8. Prompt 组装

```text
[知识库检索结果 — 请优先基于以下参考资料回答]
[参考1] （来源: <sourceName>）
<content>
...
```

保留来源名是为了让回答能给出引用，也让用户能判断答案的可信度。工具在无结果时返回 `found: false` 与可读说明，让模型知道「这是检索失败」而不是「资料里没有这句话」。

## 9. 评测

`scripts/rag_eval/` 六个脚本构成完整闭环：

| 脚本 | 作用 |
|---|---|
| `ingest.py` | 把公开语料灌入独立评测用户 |
| `build_questions.py` | 生成问题集（含无答案问题），`SEED=42`，逐题落盘可续跑 |
| `eval_rag.py` | 双路径对比（scan / sql），输出 Hit/Recall/MRR/延迟 |
| `sweep_ef.py` | `ef_search` 扫描曲线 |
| `eval_e2e.py` | 走真实链路的端到端行为验证 |
| `teardown.py` | 删除评测用户，CASCADE 清理评测数据 |

评测纪律：

- 语料与问题集隔离在独立用户下，跑完显式删除。
- 指标必须标明语料规模、问题数、索引参数、是否含无答案问题。
- 「修缺陷」与「做优化」分开表述，不允许把召回缺口包装成性能提升。
- 口径不同的两次测量不得直接相减；`RAG_EVAL.md` 中对一次错误归因做了显式撤销。

## 10. 风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| 候选集被 `LIMIT` 限死 | 召回缺口，且随语料增长恶化 | 数据库侧 Top-K，取消固定上限 |
| `ef_search` 过小 | 召回下降 | 取曲线平台区 100 |
| 规划器放弃索引 | 量到的不是索引表现 | `EXPLAIN ANALYZE` 校验执行计划；扫描实验加 `enable_seqscan = off` |
| 把向量搬回应用层 | 延迟随语料线性增长 | 返回值不含 embedding |
| `SET` 污染连接 | 影响后续业务 SQL | 使用 `SET LOCAL` |
| 阈值拍脑袋 | 该拒答时不拒答 | 用两段分布的分界点 |
| 评测污染真实数据 | 用户看到评测文档 | 独立评测用户 + teardown |
| 手工删索引后未重建 | 静默退化为顺序扫描 | 复查 `pg_indexes` |

## 11. 验证

```bash
python -m unittest tests.test_chunking -v
python scripts/rag_eval/ingest.py
python scripts/rag_eval/build_questions.py
python scripts/rag_eval/eval_rag.py
python scripts/rag_eval/sweep_ef.py
python scripts/rag_eval/eval_e2e.py
python scripts/rag_eval/teardown.py
python -m compileall -q app
```

## 12. 回滚

代码回滚不影响数据。若为实验删过索引，回滚后必须显式重建 HNSW 索引，并用 `pg_indexes` 确认物理存在——`alembic upgrade head` 对已标记应用的版本会直接跳过。
