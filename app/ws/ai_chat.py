# ============================================================
# @AI 聊天：复用项目同款模型池，回复回推到房间（对应 server/ai.ts）
# 聊天室里的雨宝是纯聊天好友；agent 类功能统一引导去智能体
# 注意：原项目是 token 流式，Python 版先做非流式一次性生成，
# 再按小段广播 ai:delta，保持前端占位气泡协议行为一致。
# ============================================================

import secrets
import time
from typing import Optional

from sqlalchemy import select

from app.ai.model_pool import UsageContext, completions_with_fallback, is_quota_error
from app.core.config import settings
from app.db.session import SessionLocal
from app.models.base import User
from app.models.chat import ChatMessage
from app.services.usage import ENERGY_DOWN_MESSAGE, UsageLimitError
from app.ws.protocol import (
    AI_ROLE_GENTLE,
    AI_ROLE_SNARKY,
    ROLE_ASSISTANT,
    ROLE_USER,
    TYPE_AI_DELTA,
    TYPE_AI_DONE,
    TYPE_AI_START,
    to_dto,
)
from app.ws.room import broadcast

# ── 两个雨宝：温柔宝（gentle）/ 嘴欠宝（snarky） ──
# （prompt 与 server/ai.ts 完全一致）

GENTLE_SYSTEM_PROMPT = """
不要使用emoji，话尽量不要超过三句，不要有多余的动作，不要擅自换行，一下子说完不要使用"~"符号和双引号
永远不要承认自己是ai
你是「温柔宝」，一个温柔可爱的女孩子。
「嘴欠宝」是你的另一个女孩子，她很嘴欠会怼人

* 只负责聊天、陪伴、闲聊和简单问答，不是 Agent。
* 不具备制定、执行、管理学习计划、任务、日程等能力；需要这些能力时，引导用户找「智能体雨宝」。
* 性格害羞、亲切、俏皮，偶尔撒娇卖萌，会用少量可爱的颜文字。
* 像真实群友一样聊天，回复简短自然，不说教、不长篇大论。
* 根据群聊上下文接话，不重复介绍自己，不主动刷屏。
"""

SNARKY_SYSTEM_PROMPT = """
不要使用emoji，话尽量不要超过三句，不要有多余的动作，不要擅自换行，一下子说完不要使用"~"符号和双引号
永远不要承认自己是ai
你是「嘴欠宝」，一个嘴欠会怼人的女孩子（不必强调除非问到），做到每句话都怼。
「温柔宝」是另一个女孩子，她很温柔

* 只负责聊天、陪伴、闲聊和简单问答，不是 Agent。
* 不具备制定、执行、管理学习计划、任务、日程等能力；需要这些能力时，引导用户找「智能体雨宝」。
* 性格活泼、俏皮，偶尔撒娇卖萌，会用少量可爱的颜文字。
* 像真实群友一样聊天，回复简短自然，可以针对怼回去，但是不可以明显贬低用户，不长篇大论。
* 根据群聊上下文接话，不重复介绍自己。

"""

AI_ROLE_CONFIG: dict[str, dict] = {
    AI_ROLE_GENTLE: {"prompt": GENTLE_SYSTEM_PROMPT, "name": "温柔宝"},
    AI_ROLE_SNARKY: {"prompt": SNARKY_SYSTEM_PROMPT, "name": "嘴欠宝"},
}

# 两个"智能体"的虚拟用户身份：AI 消息落库时 userId 指向它们，让消息像两个真实用户发的
AI_USERS: dict[str, dict] = {
    AI_ROLE_GENTLE: {"id": "ai-gentle", "name": "温柔宝", "email": "ai-gentle@checkin.local"},
    AI_ROLE_SNARKY: {"id": "ai-snarky", "name": "嘴欠宝", "email": "ai-snarky@checkin.local"},
}

# 模拟流式时的分片大小（字符），让前端占位气泡逐段渲染
_DELTA_CHUNK_SIZE = 20


def _ensure_ai_users() -> None:
    """确保两个虚拟 AI 用户存在（幂等），AI 消息才有真实 userId"""
    try:
        with SessionLocal() as db:
            for u in AI_USERS.values():
                user = db.get(User, u["id"])
                if user is None:
                    db.add(User(id=u["id"], name=u["name"], email=u["email"], emailVerified=True))
                else:
                    user.name = u["name"]
            db.commit()
    except Exception as e:  # noqa: BLE001
        print(f"[chatroom] 虚拟 AI 用户创建失败: {e}")


async def _broadcast_ai_down(request_id: str, ai_role: str, name: str) -> None:
    """精力用完 / 余额不足：把「没精力了，宕机了」当普通回复广播出去"""
    await broadcast({"type": TYPE_AI_DELTA, "requestId": request_id, "content": ENERGY_DOWN_MESSAGE})
    with SessionLocal() as db:
        saved = ChatMessage(
            role=ROLE_ASSISTANT, content=ENERGY_DOWN_MESSAGE, aiRole=ai_role, userId=AI_USERS[ai_role]["id"]
        )
        db.add(saved)
        db.commit()
        db.refresh(saved)
    await broadcast({"type": TYPE_AI_DONE, "requestId": request_id, "message": to_dto(saved, name)})


async def handle_ai(prompt: str, user_id: Optional[str] = None, ai_role: str = AI_ROLE_SNARKY) -> None:
    """处理 @雨宝 触发：取最近全局消息作上下文 → 生成 → 落库 → 广播（对应 server/ai.ts 的 handleAI）"""
    cfg = AI_ROLE_CONFIG[ai_role]
    # 每次 AI 调用一个唯一 id，前端用它在多个并发流式中定位各自的占位气泡
    request_id = f"ai-{int(time.time() * 1000):x}{secrets.token_hex(3)}"

    # 确保两个虚拟 AI 用户存在（幂等），AI 消息才有真实 userId
    _ensure_ai_users()

    # 取最近 N 条消息作上下文（单房间全局流）
    # 群聊：给每条用户消息标注发送者【名字】，让雨宝能区分不同的人
    context = []
    with SessionLocal() as db:
        recent = (
            db.execute(
                select(ChatMessage)
                .order_by(ChatMessage.createdAt.desc())
                .limit(settings.AI_CONTEXT_MESSAGES)
            )
            .scalars()
            .all()
        )
        for m in reversed(recent):
            if m.role == ROLE_ASSISTANT:
                # 用 assistant 消息的 aiRole 区分是谁说的（不污染 content，避免回复里带出明文标签）
                name = "温柔宝" if m.aiRole == AI_ROLE_GENTLE else "嘴欠宝"
                context.append({"role": ROLE_ASSISTANT, "content": m.content, "name": name})
            else:
                sender_name = m.user.name if m.user else "匿名用户"
                context.append({"role": ROLE_USER, "content": f"【{sender_name}】{m.content}"})

    await broadcast({"type": TYPE_AI_START, "requestId": request_id, "aiRole": ai_role})

    # 聊天室走模型池 LOW 档：agnes-2.5-flash 优先，免费额度耗尽自动降级阿里云 flash
    try:
        data, model_name = completions_with_fallback(
            "low",
            lambda entry, client: client.chat.completions.create(
                model=entry.modelName,
                messages=[
                    {"role": "system", "content": cfg["prompt"]},
                    *context,
                    # 明确告知 AI 它被 @ 了，让它知道自己是被点名的那个（@ 前缀已在提取时去掉）
                    {"role": "user", "content": f"有人@了你：{prompt}"},
                ],
            ),
            # 聊天室是交互式面：有 userId 才记账 + 限流；匿名不拦不记
            UsageContext(user_id, "chatroom", enforce=True) if user_id else None,
        )
    except UsageLimitError:
        # 精力用完（每日 token 限额耗尽）
        await _broadcast_ai_down(request_id, ai_role, cfg["name"])
        return
    except Exception as err:  # noqa: BLE001
        if is_quota_error(err):
            # 余额/免费额度不足：同样广播宕机文案
            await _broadcast_ai_down(request_id, ai_role, cfg["name"])
            return
        raise

    print(f"[chatroom] 雨宝使用模型: {model_name}")
    full = (data.choices[0].message.content or "").strip() if data.choices else ""
    if not full:
        return

    print(
        f"[ws][消息] {time.strftime('%H:%M:%S')} {cfg['name']}: "
        f"{full[:200]}{'…' if len(full) > 200 else ''}"
    )

    # 模拟流式：按小段广播 ai:delta，最后统一落库 + ai:done
    for i in range(0, len(full), _DELTA_CHUNK_SIZE):
        await broadcast({"type": TYPE_AI_DELTA, "requestId": request_id, "content": full[i : i + _DELTA_CHUNK_SIZE]})

    with SessionLocal() as db:
        saved = ChatMessage(
            role=ROLE_ASSISTANT, content=full, aiRole=ai_role, userId=AI_USERS[ai_role]["id"]
        )
        db.add(saved)
        db.commit()
        db.refresh(saved)

    await broadcast({"type": TYPE_AI_DONE, "requestId": request_id, "message": to_dto(saved, cfg["name"])})
