# ============================================================
# 引导模板种子（对应 prisma/seed.ts + src/lib/onboard.ts）
# - seed()：首次部署时写入全局引导模板
# - clone_guide_templates(user_id)：注册瞬间克隆给新用户
# ============================================================

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.knowledge import Document, DocumentTemplate, PlanTemplate
from app.models.study import Plan
from app.services.plan_sync import sync_tasks_from_document


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── 通关计划模板 ──
PLAN_TEMPLATE = {
    "id": "guide-plan",
    "name": "通关学习平台计划",
    "description": "按任务顺序做一遍，你就掌握了全部核心玩法。",
    "goal": "用几天时间，亲手走一遍学习平台的核心功能，完成一次完整的学习闭环。",
    "document": """# 通关学习平台计划

## 目标
用几天时间，亲手走一遍学习平台的核心功能，完成一次完整的学习闭环。

## 计划说明
这不是一份真的学习计划，而是一份「使用指南」——按任务顺序做一遍，你就掌握了全部核心玩法。

## 任务安排
- [ ] 完成一次 25 分钟的专注（你就在专注房间里，直接开一个番茄钟）
- [ ] 去小岛完成一次打卡
- [ ] 查看统计页，看看你的成长数据
- [ ] 用「新建计划」创建一个学习计划，在 AI 框里直接告诉它你的目标
- [ ] 和 AI 助手聊一次，问一个学习问题
- [ ] 在文档系统里写一篇学习笔记

## 学习笔记
在这里记录你的通关感想…
""",
}

# ── 引导文档模板 ──
DOCUMENT_TEMPLATE = {
    "id": "guide-doc",
    "title": "👋 欢迎使用学习平台",
    "content": """# 👋 欢迎使用学习平台

欢迎来到你的学习空间。计划、专注、打卡和成长记录都放在一起，让努力可量化、可回顾。

## 你的第一天
1. **开始专注**：你就在专注房间里，开一个番茄钟，试试 25 分钟心无旁骛。
2. **去小岛打卡**：在「小岛」签到，留下今天的足迹。
3. **查看成长**：在**主页**看专注时长和连续活跃。
4. **规划目标**：当你想安排一个长期目标时，点「新建计划」，在 AI 框里告诉它你的目标，它会帮你生成计划。

## 核心功能
- **计划 / 文档工作室**：Markdown 编辑 + AI 直接修改文档。
- **AI 学习助手**：结合你的数据给个性化建议。
- **知识库**：上传学习资料，AI 问答可检索引用。
- **小岛打卡**：场景随主题切换，签到让努力有迹可循。

## 最后
学习像种一棵树，今天看不见，明天也看不见，但每一个专注的 25 分钟、每一次在小岛留下的足迹，都在悄悄往土壤里扎根。真正让这棵树长大的，是你自己。

这里没有截止日期，只有温柔的见证。愿你把每一份努力种进今天，然后从容地等它发芽、生长、开花。

这篇文档属于你，可以保留、改写，也可以直接删掉。祝你学习愉快。
""",
}


def seed_templates(db: Session) -> None:
    """写入引导模板（幂等：已存在则更新）"""
    t = db.get(PlanTemplate, PLAN_TEMPLATE["id"])
    if t:
        t.name = PLAN_TEMPLATE["name"]
        t.description = PLAN_TEMPLATE["description"]
        t.goal = PLAN_TEMPLATE["goal"]
        t.document = PLAN_TEMPLATE["document"]
    else:
        db.add(PlanTemplate(**PLAN_TEMPLATE))

    d = db.get(DocumentTemplate, DOCUMENT_TEMPLATE["id"])
    if d:
        d.title = DOCUMENT_TEMPLATE["title"]
        d.content = DOCUMENT_TEMPLATE["content"]
    else:
        db.add(DocumentTemplate(**DOCUMENT_TEMPLATE))

    db.commit()
    print("✅ 引导模板已写入（通关计划 + 引导文档）")


def clone_guide_templates(db: Session, user_id: str) -> None:
    """注册瞬间：把引导模板克隆给新用户。

    - 通关计划（PlanTemplate）→ Plan：document 里的「## 任务安排」段落
      经 sync_tasks_from_document 同步成 PlanTask，新用户一进计划页就有带任务的真实计划。
    - 引导文档（DocumentTemplate）→ Document：出现在文档列表，可点开阅读/编辑/删除。
    模板缺失时静默跳过；单个失败不阻断整体，也绝不影响注册本身。
    """
    plan_templates = db.query(PlanTemplate).order_by(PlanTemplate.createdAt.asc()).all()
    for t in plan_templates:
        try:
            plan = Plan(
                userId=user_id,
                name=t.name,
                description=t.description,
                goal=t.goal,
                document=t.document,
                status="active",
            )
            db.add(plan)
            db.flush()
            if t.document:
                try:
                    sync_tasks_from_document(db, plan.id, user_id, t.document)
                except Exception as e:  # noqa: BLE001
                    print(f"[onboard] 同步任务失败: {e}")
                    db.rollback()
        except Exception as e:  # noqa: BLE001
            print(f"[onboard] 克隆计划模板失败: {e}")
            db.rollback()

    doc_templates = (
        db.query(DocumentTemplate).order_by(DocumentTemplate.createdAt.asc()).all()
    )
    for t in doc_templates:
        try:
            db.add(Document(userId=user_id, title=t.title, content=t.content))
        except Exception as e:  # noqa: BLE001
            print(f"[onboard] 克隆文档模板失败: {e}")
            db.rollback()

    db.commit()
