# ============================================================
# 内存连接管理（对应 server/room.ts）
# 单房间模式：聊天是全局一条流，所有在线连接共享同一个频道
# 单实例起步，多实例再换 Redis/Postgres NOTIFY
# ============================================================

import json
import threading
import time
from dataclasses import dataclass, field

from fastapi import WebSocket


@dataclass(eq=False)
class Connection:
    """一条在线 WebSocket 连接（对应 room.ts 的 Connection）

    eq=False：按对象身份哈希（连接是唯一实例，集合按 id 去重）。
    默认 dataclass 因含可变字段会被标记为 unhashable，add 到集合会抛 TypeError。
    """

    ws: WebSocket
    userId: str
    userName: str
    image: str | None
    is_alive: bool = True
    # 限流：窗口起点（毫秒时间戳）与窗口内已发消息数
    window_start: int = field(default_factory=lambda: int(time.time() * 1000))
    message_count: int = 0
    # 幂等去重（记录最近处理过的 clientId）
    seen_client_ids: set[str] = field(default_factory=set)
    # 最近活跃时间（毫秒时间戳）：心跳兜底清理用
    last_seen: int = field(default_factory=lambda: int(time.time() * 1000))


# 全局在线连接集合
_connections: set[Connection] = set()
_lock = threading.Lock()


def add_connection(c: Connection) -> None:
    with _lock:
        _connections.add(c)


def remove_connection(c: Connection) -> None:
    with _lock:
        _connections.discard(c)


def all_connections() -> set[Connection]:
    """返回在线连接快照（副本，避免遍历时与增删并发冲突）"""
    with _lock:
        return set(_connections)


async def broadcast(message) -> None:
    """全局广播给所有在线连接（对应 room.ts 的 broadcast）"""
    data = json.dumps(message, ensure_ascii=False)
    for c in all_connections():
        try:
            await c.ws.send_text(data)
        except Exception:  # noqa: BLE001
            # 发送失败（连接已断开/被关闭），忽略，交给 receive 循环的 close 清理
            pass
