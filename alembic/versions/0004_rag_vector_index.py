"""add hnsw index on documentchunk.embedding (RAG 向量检索)

Revision ID: 0004_rag_vector_index
Revises: 0003_garden_matured
Create Date: 2026-09-13

背景：documentchunk.embedding 从建表起就是 pgvector 的 Vector(1024)，
但检索路径是「SQL 全量捞出（且被 limit(1000) 截断）→ Python 逐条算余弦」，
索引从未参与查询，扩容后既是性能瓶颈也是召回缺口。这里补上近邻索引，
让 Top-K 回到数据库侧完成。

参数取舍：
  - HNSW 而非 IVFFlat：IVFFlat 需要先有数据才能训练出合理的聚类中心，
    且对增量插入不友好；HNSW 无训练阶段，适合「随时导入文档」的场景。
  - vector_cosine_ops：与检索侧 <==> 余弦距离算子配套，语义与原有余弦一致。
  - m=16 / ef_construction=64：pgvector 默认值，中小规模语料足够；
    召回不足时优先调查询期的 hnsw.ef_search，而不是重建索引。
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "0004_rag_vector_index"
down_revision = "0003_garden_matured"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_docchunk_embedding_hnsw "
        "ON documentchunk USING hnsw (embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_docchunk_embedding_hnsw")
