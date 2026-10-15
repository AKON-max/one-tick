# ============================================================
# 引导模板种子
# - seed()：首次部署时写入全局引导模板
# - clone_guide_templates(user_id)：注册瞬间克隆给新用户
# - seed_guest_demo(user_id)：游客登录时铺一份演示数据
# ============================================================

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models.garden import Garden
from app.models.knowledge import Document, DocumentTemplate, PlanTemplate
from app.models.misc import Notification
from app.models.study import Checkin, Plan, StudyRecord, Todo
from app.services.plan_sync import sync_tasks_from_document


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── 通关计划模板 ──
PLAN_TEMPLATE = {
    "id": "guide-plan",
    "name": "通关 One-Tick 计划",
    "description": "按任务顺序做一遍，你就掌握了全部核心玩法。",
    "goal": "用几天时间，亲手走一遍 One-Tick 的核心功能，完成一次完整的学习闭环。",
    "document": """# 通关 One-Tick 计划

## 目标
用几天时间，亲手走一遍 One-Tick 的核心功能，完成一次完整的学习闭环。

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
    "title": "👋 欢迎使用 One-Tick",
    "content": """# 👋 欢迎使用 One-Tick

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
学习像种一棵树，今天看不见，明天也看不见，但每一个专注的 25 分钟、每一次在小岛留下的足迹，都在悄悄往土壤里扎根。One-Tick 不会催促你，它只是站在你身边，把你的每一步记进风景里——真正让这棵树长大的，是你自己。

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


# ── 游客演示数据 ──

#: 演示打卡历史天数（含今天）。游客账号的 createdAt 也回填到这一天，
#: 否则资料页会出现「加入 1 天 / 已打卡 10 天」的矛盾
GUEST_DEMO_DAYS = 10
#: 演示科目（轮换，让学科分布图不为空）
_DEMO_SUBJECTS = ["英语", "算法", "Python", "数学"]

#: 近 7 天每天的专注场次（分钟，由 6 天前递进到今天）。
#: 刻意每天不同：若每天都是同一个时长，统计页的柱状图会是一条平线，
#: 游客看不出「一根柱子 = 当天专注了多少分钟」这层含义。
#: 单场时长取番茄钟档位里的 25 / 45 分钟。
_DEMO_FOCUS_SESSIONS: tuple[tuple[float, ...], ...] = (
    (25.0,),                # 6 天前
    (45.0,),                # 5 天前
    (25.0, 25.0),           # 4 天前
    (25.0, 45.0, 25.0),     # 3 天前
    (25.0,),                # 2 天前
    (45.0, 45.0),           # 1 天前
    (25.0, 45.0),           # 今天
)

#: 演示通知：（type, 标题, 正文, 跳转, 几天前）。
#: 游客进来最想知道「这里能做什么」，所以鼓励 / 提醒 / 系统三类各给一条。
#: 文案必须与上面已铺好的演示数据对得上（连续 10 天打卡、4 条待办里 1 条已完成），
#: 否则通知说的和页面显示的对不上，反而更露馅。
_DEMO_NOTIFICATIONS: tuple[tuple[str, str, str, str, int], ...] = (
    (
        "encouragement",
        "连续打卡 10 天，节奏已经稳了",
        "这是你连续打卡的第 10 天。稳定比冲刺更难得，保持这个节奏就好。",
        "/statistics",
        0,
    ),
    (
        "reminder",
        "待办里还有 3 件事没做完",
        "「背 30 个单词」「复习昨天的错题」「预习明天的新章节」还在等你，挑一件先专注 25 分钟。",
        "/dashboard",
        0,
    ),
    (
        "system",
        "欢迎来到 One-Tick 一刻",
        "计划、专注、打卡、文档和 AI 助手都在这里。想先了解怎么用，可以打开「阅读」里的《欢迎使用 One-Tick》。",
        "/docs",
        GUEST_DEMO_DAYS - 1,
    ),
)


def seed_guest_demo(db: Session, user_id: str) -> None:
    """给游客账号铺一份演示数据。

    游客的诉求是"进去看看里面长什么样"，空账号什么都看不出来，所以补上：
    - 打卡：最近 GUEST_DEMO_DAYS 天连续（含今天）→ 小岛 / 热力图 / 连续天数都有内容
    - 专注：近 7 天每天 1~3 场、且每天时长不同 → 统计页趋势图能看出「柱高=当天分钟数」
    - 待办：4 条（其中 1 条已完成）
    - 通知：鼓励 / 提醒 / 系统各一条 → 顶栏铃铛有未读，点进去就能看到功能入口
    - 盆栽：10 次成熟收获 → 小岛上有 10 棵树；当前盆栽浇到第 3 阶段
    写入失败不阻断游客登录（与注册钩子同样的容错策略）。
    """
    now = datetime.now(timezone.utc)
    try:
        for i in range(GUEST_DEMO_DAYS - 1, -1, -1):
            day = now - timedelta(days=i)
            subject = _DEMO_SUBJECTS[i % len(_DEMO_SUBJECTS)]
            hours = 1.0 + (i % 4) * 0.5
            db.add(
                Checkin(
                    userId=user_id,
                    content=f"{subject} · 学习 {hours:g} 小时",
                    hours=hours,
                    subject=subject,
                    checkinDate=day,
                    createdAt=day,
                )
            )

        for offset, sessions in enumerate(_DEMO_FOCUS_SESSIONS):
            day = now - timedelta(days=len(_DEMO_FOCUS_SESSIONS) - 1 - offset)
            for minutes in sessions:
                db.add(
                    StudyRecord(
                        userId=user_id,
                        date=day,
                        totalMinutes=minutes,
                        checkinId=f"focus-{uuid4().hex}",
                        createdAt=day,
                    )
                )

        for title, completed in (
            ("整理今天的学习笔记", True),
            ("背 30 个单词", False),
            ("复习昨天的错题", False),
            ("预习明天的新章节", False),
        ):
            db.add(Todo(userId=user_id, title=title, completed=completed))

        for ntype, title, content, action_url, days_ago in _DEMO_NOTIFICATIONS:
            db.add(
                Notification(
                    userId=user_id,
                    type=ntype,
                    title=title,
                    content=content,
                    actionUrl=action_url,
                    createdAt=now - timedelta(days=days_ago),
                )
            )

        db.add(Garden(userId=user_id, energy=35, wateredCount=3, maturedCount=10))
        db.commit()
    except Exception as e:  # noqa: BLE001
        print(f"[onboard] 游客演示数据写入失败: {e}")
        db.rollback()
