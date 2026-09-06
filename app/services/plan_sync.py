# ============================================================
# 计划文档「## 任务安排」段落 ↔ PlanTask 双向同步
# 对应原项目 src/lib/studio/plan-sync.ts
#
# 解析 + 差异计算：保存文档时按标题匹配 → 勾选状态更新（done/pending）+ 新增任务；
# **不删除**（保守策略，防误删进度）。
# ============================================================

import re
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.study import PlanTask


def parse_task_section(markdown: str) -> list[dict]:
    """解析文档中「## 任务安排」（或「## 任务清单」）段落，返回任务行列表

    每项: {"title": str, "done": bool}
    """
    lines = markdown.split("\n")
    items: list[dict] = []
    in_section = False
    for line in lines:
        stripped = line.strip()
        # 段落起始标题（兼容 任务安排 / 任务清单 两种叫法）
        if re.match(r"^#{1,6}\s*(任务安排|任务清单)\s*$", stripped):
            in_section = True
            continue
        # 遇到下一个任意标题 → 段落结束
        if in_section and re.match(r"^#{1,6}\s+", stripped):
            break
        if not in_section:
            continue
        # GFM 任务行：- [ ] / - [x]
        m = re.match(r"^\s*[-*+]\s+\[([ xX])\]\s+(.+?)\s*$", line)
        if m:
            items.append(
                {
                    "title": m.group(2).strip(),
                    "done": m.group(1).lower() == "x",
                }
            )
    return items


def _normalize_title(title: str) -> str:
    return re.sub(r"\s+", " ", title.strip().lower())


def sync_tasks_from_document(
    db: Session, plan_id: str, user_id: str, document: str
) -> dict:
    """将文档中的任务安排段落同步到 PlanTask 表。

    - 已存在的任务（按归一化标题匹配）：只同步勾选状态 done/pending
    - 文档里新增的任务：创建（默认 study / normal / pending）
    - 不删除任何任务（保守策略）
    """
    items = parse_task_section(document)
    if not items:
        return {"created": 0, "updated": 0}

    existing = (
        db.query(PlanTask)
        .filter(PlanTask.planId == plan_id)
        .all()
    )
    by_title = {_normalize_title(t.title): t for t in existing}

    created = 0
    updated = 0

    for item in items:
        match = by_title.get(_normalize_title(item["title"]))
        if match:
            # 只同步 done ↔ 非 done（文档勾选状态）；
            # in_progress / skipped 语义不因勾选框被动降级
            is_done = match.status == "done"
            if item["done"] != is_done:
                next_status = "done" if item["done"] else "pending"
                match.status = next_status
                match.completedAt = datetime.now(timezone.utc) if item["done"] else None
                updated += 1
        else:
            db.add(
                PlanTask(
                    planId=plan_id,
                    userId=user_id,
                    title=item["title"],
                    status="done" if item["done"] else "pending",
                    completedAt=datetime.now(timezone.utc) if item["done"] else None,
                    category="study",
                    priority="normal",
                )
            )
            created += 1

    db.commit()
    return {"created": created, "updated": updated}
