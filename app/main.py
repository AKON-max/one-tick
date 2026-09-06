# ============================================================
# FastAPI 应用入口（对应 src/app/ 入口 + server/index.ts 的健康检查）
# 挂载全部 REST 路由 + WebSocket 聊天室端点（/ws）
# ============================================================

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config import settings
from app.routers import (
    auth,
    chat,
    checkin,
    statistics,
    todos,
    focus,
    plans,
    conversations,
    ai,
    agent,
    notifications,
    documents,
    knowledge,
    oss,
    user,
    usage,
)
from app.ws import chat as ws_chat


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时：启动聊天室心跳清理任务（对应 server/index.ts 的 heartbeat）
    print(f"[{settings.APP_NAME}] 启动中...")
    heartbeat_task = asyncio.create_task(ws_chat.heartbeat_loop())
    yield
    heartbeat_task.cancel()
    print(f"[{settings.APP_NAME}] 已停止")


app = FastAPI(
    title="Python Checkin",
    description="全栈学习打卡平台（Python 版）— 打卡 · 计划 · 专注 · AI 助手 · 知识库",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
def health():
    """健康检查（对应原项目 server/index.ts 的 /health）"""
    return {"status": "ok"}


# ---- 路由挂载 ----
app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(checkin.router)
app.include_router(statistics.router)
app.include_router(todos.router)
app.include_router(focus.router)
app.include_router(plans.router)
app.include_router(conversations.router)
app.include_router(ai.router)
app.include_router(agent.router)
# ---- 附属能力：OSS 上传 / 通知 / 知识库文档 / 文档工作室 / 用户头像 ----
app.include_router(notifications.router)
app.include_router(documents.router)
app.include_router(knowledge.router)
app.include_router(oss.router)
app.include_router(user.router)
app.include_router(usage.router)
# ---- WebSocket 聊天室（对应 server/index.ts 的 /ws）----
app.include_router(ws_chat.router)
