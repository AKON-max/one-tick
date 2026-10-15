# ============================================================
# 消息协议：客户端 ↔ 服务端 之间的类型化 JSON 消息
# 每条消息都是 { type, ...payload }，type 决定字段
# 单房间模式：聊天是全局一条流，没有 roomId
# ============================================================

from datetime import datetime, timezone

# ---- 消息角色 ----
ROLE_USER = "user"
ROLE_ASSISTANT = "assistant"
ROLE_SYSTEM = "system"

# ---- 聊天室 AI 角色：温柔宝 / 嘴欠宝 ----
AI_ROLE_GENTLE = "gentle"
AI_ROLE_SNARKY = "snarky"

# ---- 服务端 → 客户端 ----
TYPE_READY = "ready"
TYPE_MESSAGE = "message"
TYPE_AI_START = "ai:start"
TYPE_AI_DELTA = "ai:delta"
TYPE_AI_DONE = "ai:done"
TYPE_PRESENCE = "presence"
TYPE_PONG = "pong"
TYPE_ERROR = "error"

# ---- 客户端 → 服务端 ----
TYPE_CLIENT_MESSAGE = "message"
TYPE_CLIENT_PING = "ping"


def iso_z(dt: datetime) -> str:
    """datetime → ISO 8601 UTC 字符串（带 Z，与 JS toISOString() 一致）"""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def to_dto(msg, user_name, image=None) -> dict:
    """将 DB 记录转为前端 DTO"""
    role = msg.role if msg.role in (ROLE_ASSISTANT, ROLE_SYSTEM) else ROLE_USER
    return {
        "id": msg.id,
        "userId": msg.userId,
        "userName": user_name,
        "image": image,
        "role": role,
        "content": msg.content,
        "createdAt": iso_z(msg.createdAt),
    }
