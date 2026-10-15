# 一次性修复：把存量账号里克隆出去的旧版引导文档 / 通关计划，刷成 One-Tick 版
#
# 背景：引导文档和通关计划是「注册瞬间从模板克隆一份给用户」，所以改了模板
# （app/services/onboard.py）只会影响之后的新账号，老账号里那份副本仍是旧标题。
# 本脚本把老副本一起刷掉。
#
# 匹配规则：只认标题 / 计划名仍等于旧模板的那一行，用户改过名的一律不碰。
# 计划文档里的「## 任务安排」段落新旧一致，所以任务列表不会因此失效，无需重新同步任务。
#
# 跑法（scripts/ 在 .dockerignore 里，镜像内没有本文件，必须先拷进去）：
#   docker cp scripts/refresh_guide_templates.py one-tick-app-1:/app/refresh_guide_templates.py
#   docker compose exec -T app python refresh_guide_templates.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.knowledge import Document
from app.models.study import Plan
from app.services.onboard import DOCUMENT_TEMPLATE, PLAN_TEMPLATE

#: 改名前那一版的标题 / 计划名
OLD_DOC_TITLE = "👋 欢迎使用学习平台"
OLD_PLAN_NAME = "通关学习平台计划"


def main() -> None:
    with SessionLocal() as db:
        docs = (
            db.execute(select(Document).where(Document.title == OLD_DOC_TITLE)).scalars().all()
        )
        for d in docs:
            d.title = DOCUMENT_TEMPLATE["title"]
            d.content = DOCUMENT_TEMPLATE["content"]

        plans = db.execute(select(Plan).where(Plan.name == OLD_PLAN_NAME)).scalars().all()
        for p in plans:
            p.name = PLAN_TEMPLATE["name"]
            p.description = PLAN_TEMPLATE["description"]
            p.goal = PLAN_TEMPLATE["goal"]
            p.document = PLAN_TEMPLATE["document"]

        db.commit()
        print(f"文档刷新 {len(docs)} 篇，计划刷新 {len(plans)} 个")


if __name__ == "__main__":
    main()
