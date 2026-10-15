import unittest

from app.ai.rag.chunk import split_markdown, split_text


class ChunkingTest(unittest.TestCase):
    def test_empty_text_returns_no_chunks(self):
        self.assertEqual(split_text(""), [])
        self.assertEqual(split_text("   "), [])

    def test_short_paragraphs_remain_separate_chunks(self):
        chunks = split_text("第一段内容。\n\n第二段内容。", chunk_size=100, overlap=10)
        self.assertEqual(["第一段内容。", "第二段内容。"], chunks)

    def test_markdown_keeps_heading_with_section(self):
        chunks = split_markdown("# 计划\n\n## 第一阶段\n完成基础学习。\n\n## 第二阶段\n完成项目。")
        self.assertTrue(any(chunk.startswith("## 第一阶段") for chunk in chunks))
        self.assertTrue(any(chunk.startswith("## 第二阶段") for chunk in chunks))

    def test_chunk_size_is_respected_for_long_paragraph(self):
        text = "甲" * 1200
        chunks = split_text(text, chunk_size=500, overlap=50)
        self.assertGreaterEqual(len(chunks), 3)
        self.assertTrue(all(len(chunk) <= 500 for chunk in chunks))


if __name__ == "__main__":
    unittest.main()