# ============================================================
# WebSocket 聊天端点（对应 server/index.ts）
# 职责：实时聊天（单房间全局流）+ @AI 回复
# 路由：/ws?token=xxx（由 app/main.py include 注册）
# ============================================================

import asyncio
import json
import re
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.config import settings
from app.core.security import decode_token
from app.db.session import SessionLocal
from app.models.base import User
from app.models.chat import ChatMessage
from app.ws.ai_chat import handle_ai
from app.ws.protocol import (
    AI_ROLE_GENTLE,
    AI_ROLE_SNARKY,
    TYPE_CLIENT_MESSAGE,
    TYPE_CLIENT_PING,
    TYPE_ERROR,
    TYPE_MESSAGE,
    TYPE_PONG,
    TYPE_PRESENCE,
    TYPE_READY,
    to_dto,
)
from app.ws.room import Connection, add_connection, all_connections, broadcast, remove_connection

router = APIRouter()

# 会话 cookie 名：前端 FastAPI 登录写入的 JWT cookie；兼容旧 better-auth 名
SESSION_COOKIE_NAME = "session_token"
SESSION_COOKIE_LEGACY = "better-auth.session_token"

# 幂等去重缓冲上限（对应 index.ts 的 200）
MAX_SEEN_CLIENT_IDS = 200

# WS 关闭码：未登录/鉴权失败
CLOSE_CODE_UNAUTHORIZED = 1008


async def heartbeat_loop() -> None:
    """服务端定期检查连接活跃度，超时未响应则断开（对应 index.ts 的心跳清理）"""
    timeout_ms = settings.HEARTBEAT_INTERVAL_MS * 2
    while True:
        await asyncio.sleep(settings.HEARTBEAT_INTERVAL_MS / 1000)
        now = int(time.time() * 1000)
        for c in all_connections():
            if now - c.last_seen > timeout_ms:
                try:
                    await c.ws.close(code=1001)
                except Exception:  # noqa: BLE001
                    pass


@router.websocket("/ws")
async def ws_chat(websocket: WebSocket) -> None:
    """聊天室 WebSocket 端点：/ws?token=xxx（token 也可放 cookie）"""
    # ---- 握手鉴权：从 query param 或 cookie 读 JWT（对应 index.ts 的 upgrade 鉴权）----
    token = websocket.query_params.get("token")
    if not token:
        token = (
            websocket.cookies.get(SESSION_COOKIE_NAME)
            or websocket.cookies.get(SESSION_COOKIE_LEGACY)
            or websocket.cookies.get("token")
        )
    payload = decode_token(token) if token else None
    if payload is None or not payload.get("sub"):
        # 未登录 / token 失效：直接关闭（对应 HTTP 401）
        await websocket.close(code=CLOSE_CODE_UNAUTHORIZED)
        return
    user_id = payload["sub"]

    # 从数据库取用户最新昵称/头像
    with SessionLocal() as db:
        user = db.get(User, user_id)
        if user is None:
            await websocket.close(code=CLOSE_CODE_UNAUTHORIZED)
            return
        user_name = user.name or "匿名"
        image = user.image

    # FastAPI 要求先 accept 才能收发消息（鉴权失败走 close 则无需 accept）
    await websocket.accept()

    conn = Connection(ws=websocket, userId=user_id, userName=user_name, image=image)
    add_connection(conn)
    try:
        # 通知所有在线连接：在线人数变化
        await broadcast({"type": TYPE_PRESENCE, "online": len(all_connections())})
        # ready：发用户信息
        await websocket.send_text(
            json.dumps(
                {"type": TYPE_READY, "user": {"id": user_id, "name": user_name, "image": image}},
                ensure_ascii=False,
            )
        )

        # ---- 消息接收循环 ----
        while True:
            raw = await websocket.receive_text()
            conn.last_seen = int(time.time() * 1000)
            try:
                msg = json.loads(raw)
            except (json.JSONDecodeError, ValueError):
                await _send_error(conn, "invalid_json", "消息格式错误")
                continue
            if not isinstance(msg, dict):
                await _send_error(conn, "invalid_json", "消息格式错误")
                continue

            msg_type = msg.get("type")
            if msg_type == TYPE_CLIENT_PING:
                # ping → pong
                await conn.ws.send_text(json.dumps({"type": TYPE_PONG}))
            elif msg_type == TYPE_CLIENT_MESSAGE:
                await _handle_user_message(conn, msg)
            else:
                await _send_error(conn, "unknown_type", "未知消息类型")
    except WebSocketDisconnect:
        pass
    except Exception as exc:  # noqa: BLE001
        # 其它异常（连接中断等）同样走 finally 清理，仅打日志便于排查
        print(f"[ws] 连接异常 user={user_id}: {type(exc).__name__}: {exc}")
    finally:
        remove_connection(conn)
        await broadcast({"type": TYPE_PRESENCE, "online": len(all_connections())})


async def _handle_user_message(conn: Connection, msg: dict) -> None:
    """处理客户端 message（对应 index.ts 的 handleUserMessage）"""
    content = str(msg.get("content") or "").strip()
    client_id = str(msg.get("clientId") or "")
    if not content:
        return
    if len(content) > settings.MAX_MESSAGE_LENGTH:
        await _send_error(conn, "too_long", "消息过长")
        return
    if not _check_rate_limit(conn):
        await _send_error(conn, "rate_limited", "发送太频繁，稍后再试")
        return
    # 幂等去重：同一 clientId 只处理一次
    if client_id in conn.seen_client_ids:
        return
    conn.seen_client_ids.add(client_id)
    if len(conn.seen_client_ids) > MAX_SEEN_CLIENT_IDS:
        conn.seen_client_ids.pop()

    # 落库 + 用数据库里的最新昵称/头像（用户可能中途换了头像，conn 里是连接时的旧值）
    with SessionLocal() as db:
        saved = ChatMessage(userId=conn.userId, role="user", content=content)
        db.add(saved)
        db.commit()
        db.refresh(saved)
        sender = db.get(User, conn.userId)
        user_name = sender.name if sender and sender.name else conn.userName
        image = sender.image if sender else conn.image
        conn.userName = user_name
        conn.image = image

    print(
        f"[ws][消息] {time.strftime('%H:%M:%S')} {user_name}: "
        f"{content[:100]}{'…' if len(content) > 100 else ''}"
    )

    await broadcast({"type": TYPE_MESSAGE, "message": to_dto(saved, user_name, image)})

    # @AI 触发（传 userId，聊天室按用户记账 + 每日限额）；一条消息可同时 @温柔宝 + @嘴欠宝，各自回复
    for prompt, ai_role in _extract_ai_prompts(content):
        asyncio.create_task(handle_ai(prompt, conn.userId, ai_role))


async def _send_error(conn: Connection, code: str, reason: str) -> None:
    """给单条连接发错误（对应 index.ts 的 sendError）"""
    try:
        await conn.ws.send_text(
            json.dumps({"type": TYPE_ERROR, "code": code, "reason": reason}, ensure_ascii=False)
        )
    except Exception:  # noqa: BLE001
        pass


def _check_rate_limit(conn: Connection) -> bool:
    """滑动窗口限流（对应 index.ts 的 checkRateLimit）"""
    now = int(time.time() * 1000)
    if now - conn.window_start > settings.RATE_LIMIT_WINDOW_MS:
        conn.window_start = now
        conn.message_count = 0
    conn.message_count += 1
    return conn.message_count <= settings.RATE_LIMIT_MAX


# @温柔宝 → 温柔宝；@雨宝 / @嘴欠宝 / @AI → 嘴欠宝；/ai 是命令式，仍要求开头（避免命中 /api 之类）
_AI_MENTION_RE = re.compile(r"@温柔宝|@嘴欠宝|@雨宝|@AI|^\s*/ai(?=\s|$)", re.IGNORECASE)


def _extract_ai_prompts(content: str) -> list[tuple[str, str]]:
    """提取 @AI 触发（对应 index.ts 的 extractAIPrompts）；返回 [(prompt, ai_role), ...]"""
    results: list[tuple[str, str]] = []
    for m in _AI_MENTION_RE.finditer(content):
        token = m.group(0)
        ai_role = AI_ROLE_GENTLE if "温柔" in token else AI_ROLE_SNARKY
        # 优先取提及之后的文字作为提问
        after = content[m.end() :].lstrip().strip()
        prompt = after or content[: m.start()].strip() or None
        if prompt:
            results.append((prompt, ai_role))
    # 同角色只触发一次（一条消息 @ 同一个人两次不重复回复）
    deduped: list[tuple[str, str]] = []
    seen_roles: set[str] = set()
    for prompt, ai_role in results:
        if ai_role in seen_roles:
            continue
        seen_roles.add(ai_role)
        deduped.append((prompt, ai_role))
    return deduped
