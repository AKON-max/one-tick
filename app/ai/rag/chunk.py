# ============================================================
# RAG 文本分片工具
#
# 两种策略:
#   ① split_text       — 固定大小 + 重叠（通用，适合纯文本/PDF）
#   ② split_markdown   — 按 ## 标题语义分片（适合 Markdown）
#
# bge-m3 最大输入 8192 tokens，默认 chunk 500 字留足余量
# ============================================================

import re

# 句子断点：中文 + 英文（顺序敏感，中文优先）
_SENTENCE_SEPS = ["。", "？", "！", ".", "?", "!"]


def split_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    """固定大小 + 重叠分片

    :param text:       原始文本
    :param chunk_size: 每个 chunk 的字数（默认 500）
    :param overlap:    相邻 chunk 重叠字数（默认 50）
    :return: 分片后的文本数组
    """
    if not text or not text.strip():
        return []

    # 先按段落分割，避免在句子中间切断
    paragraphs = re.split(r"\n{2,}", text)
    chunks: list[str] = []

    for para in paragraphs:
        trimmed = para.strip()
        if not trimmed:
            continue

        # 短段落直接作为一个 chunk
        if len(trimmed) <= chunk_size:
            chunks.append(trimmed)
            continue

        # 长段落按固定大小切分
        start = 0
        while start < len(trimmed):
            end = min(start + chunk_size, len(trimmed))
            chunk = trimmed[start:end]

            # 尽量在句号、问号、感叹号处断开（中文+英文）
            if end < len(trimmed):
                for sep in _SENTENCE_SEPS:
                    last_sep = chunk.rfind(sep)
                    if last_sep > chunk_size * 0.6:
                        chunk = chunk[: last_sep + 1]
                        break

            chunk = chunk.strip()
            if not chunk:
                break  # 安全兜底

            chunks.append(chunk)

            # 已切到文本末尾：结束。
            # 否则尾部（≤ overlap 的小尾巴）会让 advance ≤ 0、被强制成 1，
            # 退化成"每次前进 1 字"的重复重叠分片。
            if end >= len(trimmed):
                break

            # 确保 start 始终前进（防止死循环）
            advance = len(chunk) - overlap
            start += advance if advance > 0 else 1

    print(f"[Chunk] {len(text)} 字 → {len(chunks)} 个分片 (size={chunk_size}, overlap={overlap})")
    return chunks


def split_markdown(text: str, max_chunk_size: int = 800) -> list[str]:
    """按 Markdown 标题（## 级别）语义分片

    适合结构良好的 Markdown 文档，每个 ## 段落为一个 chunk。
    如果某个段落过长，内部再用 split_text 切分。

    :param text:           原始 Markdown 文本
    :param max_chunk_size: 单个 chunk 的最大字数（默认 800）
    :return: 分片后的文本数组
    """
    if not text or not text.strip():
        return []

    chunks: list[str] = []

    # 按 ## 标题分割
    sections = re.split(r"\n(?=## )", text)

    for section in sections:
        trimmed = section.strip()
        if not trimmed:
            continue

        if len(trimmed) <= max_chunk_size:
            chunks.append(trimmed)
        else:
            # 保留标题行，对正文做固定大小切分
            lines = trimmed.split("\n")
            heading = lines[0]
            body = "\n".join(lines[1:])
            body_chunks = split_text(body, max_chunk_size, 50)
            for bc in body_chunks:
                chunks.append(f"{heading}\n{bc}")

    print(f"[Chunk] Markdown {len(text)} 字 → {len(chunks)} 个分片")
    return chunks
