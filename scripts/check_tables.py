# 验证数据库表创建情况（临时脚本）
from sqlalchemy import create_engine, text

engine = create_engine("postgresql+psycopg2://postgres:postgres@localhost:5432/python_checkin")
with engine.connect() as conn:
    rows = conn.execute(
        text("select tablename from pg_tables where schemaname='public' order by tablename")
    ).fetchall()
    print(f"共 {len(rows)} 张表:")
    for r in rows:
        print(" -", r[0])
