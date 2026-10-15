import unittest

from pydantic import ValidationError

from app.ai.agent.service import MAX_TASKS
from app.ai.agent.types import PlanDraft, TaskDraft
from app.ai.rag.client import BATCH_SIZE
from app.ai.rag.retriever import HNSW_EF_SEARCH
from app.models.garden import MAX_STAGE, WATER_COST
from app.routers.ai import MAX_CONTEXT_MESSAGES, MAX_CONTEXT_ROUNDS


class DesignContractTest(unittest.TestCase):
    def test_chat_context_contract(self):
        self.assertEqual(20, MAX_CONTEXT_ROUNDS)
        self.assertEqual(40, MAX_CONTEXT_MESSAGES)

    def test_rag_contract(self):
        self.assertEqual(10, BATCH_SIZE)
        self.assertEqual(100, HNSW_EF_SEARCH)

    def test_garden_contract(self):
        self.assertEqual(4, MAX_STAGE)
        self.assertEqual(25, WATER_COST)

    def test_plan_draft_limits(self):
        self.assertEqual(40, MAX_TASKS)
        with self.assertRaises(ValidationError):
            PlanDraft(name="x", goal="y", tasks=[TaskDraft(title="t")] * 41)


if __name__ == "__main__":
    unittest.main()