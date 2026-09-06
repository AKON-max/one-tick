# 运行引导模板种子（临时脚本）
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.services.onboard import seed_templates

with SessionLocal() as db:
    seed_templates(db)
    print("种子写入完成")
