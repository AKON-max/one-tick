import unittest

from app.services.plan_sync import parse_task_section


class PlanSyncTest(unittest.TestCase):
    def test_parses_task_checkboxes(self):
        markdown = """# 计划

## 任务安排

- [x] 完成环境搭建
- [ ] 完成第一章
- [X] 提交复盘

## 学习笔记

- [ ] 这段不属于任务
"""
        items = parse_task_section(markdown)
        self.assertEqual(
            [
                {"title": "完成环境搭建", "done": True},
                {"title": "完成第一章", "done": False},
                {"title": "提交复盘", "done": True},
            ],
            items,
        )

    def test_returns_empty_without_task_section(self):
        self.assertEqual([], parse_task_section("# 计划\n\n只有正文"))


if __name__ == "__main__":
    unittest.main()