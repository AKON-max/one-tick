# ============================================================
# FastAPI 应用入口
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
    garden,
)
from app.ws import chat as ws_chat


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动聊天室心跳清理任务
    print(f"[{settings.APP_NAME}] 启动中...")
    heartbeat_task = asyncio.create_task(ws_chat.heartbeat_loop())
    yield
    heartbeat_task.cancel()
    print(f"[{settings.APP_NAME}] 已停止")


app = FastAPI(
    title="One-Tick API",
    description="One-Tick 一刻 — 学习计划、专注、AI 助手与知识库 API",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
def health():
    """健康检查"""
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
# ---- 植物农场 ----
app.include_router(garden.router)
# ---- WebSocket 聊天室 ----
app.include_router(ws_chat.router)
