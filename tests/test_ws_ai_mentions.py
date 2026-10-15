import unittest

from app.ws.chat import _extract_ai_prompts


class AiMentionTest(unittest.TestCase):
    def test_gentle_mention(self):
        self.assertEqual([("帮我看看计划", "gentle")], _extract_ai_prompts("@温柔宝 帮我看看计划"))

    def test_default_ai_mention_uses_snarky_role(self):
        self.assertEqual([("你好", "snarky")], _extract_ai_prompts("@AI 你好"))

    def test_same_role_is_deduplicated(self):
        result = _extract_ai_prompts("@温柔宝 你好 @温柔宝 再来一次")
        self.assertEqual(1, len(result))
        self.assertEqual("gentle", result[0][1])

    def test_command_form(self):
        self.assertEqual([("解释链表", "snarky")], _extract_ai_prompts("/ai 解释链表"))


if __name__ == "__main__":
    unittest.main()