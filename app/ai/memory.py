# ============================================================
# 长期记忆系统升级
#
# 升级内容：
# ① type       — 记忆分类细化（goal/habit/preference/skill/weakness/fact）
# ② importance — AI 判断的重要性评分 0-1
# ③ confidence — AI 对记忆准确性的置信度 0-1
# ④ lastUsed   — 上次被检索时间，用于淘汰冷记忆
#
# 新增能力：
# ⑤ get_important_memories — 按重要性排序查询（Agent 用）
# ⑥ touch_memories         — 标记记忆被使用
# ⑦ 智能去重               — AI 判断匹配到已有记忆则更新而不新建
# ============================================================

import json
from datetime import datetime, timezone
from typing import Any, Literal, Optional

from sqlalchemy import delete, select, update

from app.ai.model_pool import completions_with_fallback
from app.ai.rag.client import embed_text
from app.ai.rag.retriever import cosine_similarity, parse_embedding
from app.db.session import SessionLocal
from app.models.agent import UserMemory

# ---- 类型 ----

# 记忆类型（比旧版 category 更细粒度，字符串字面量）
MemoryType = Literal["goal", "habit", "preference", "skill", "weakness", "fact"]


def _now() -> datetime:
    """当前 UTC 时间（与模型默认值一致）"""
    return datetime.now(timezone.utc)


def _clamp_score(value: Any) -> float:
    """将 AI 返回的分数限制在 0-1（非法值兜底 0.5）"""
    try:
        v = float(value)
    except (TypeError, ValueError):
        v = 0.5
    return max(0.0, min(1.0, v))


def _recency_score(created_at: datetime, now: Optional[datetime] = None) -> float:
    """时间衰减分：最近 7 天为 1.0，30 天内线性衰减到 0.1，超过 30 天为 0.05"""
    if now is None:
        now = _now()
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    else:
        created_at = created_at.astimezone(timezone.utc)
    age_days = (now - created_at).total_seconds() / 86400.0
    if age_days <= 7:
        return 1.0
    if age_days <= 30:
        # 7 天 = 1.0 → 30 天 = 0.1 线性衰减
        return 1.0 - (age_days - 7) * (1.0 - 0.1) / (30 - 7)
    return 0.05


def _memory_to_dict(m: UserMemory) -> dict:
    """ORM 行 → dict，字段名与 TS UserMemory 保持一致"""
    return {
        "id": m.id,
        "content": m.content,
        "type": m.type,
        "importance": m.importance,
        "confidence": m.confidence,
        "lastUsed": m.lastUsed,
        "createdAt": m.createdAt,
    }


# ---- 查询 ----

def get_relevant_memories(
    user_id: str,
    limit: int = 20,
    query: Optional[str] = None,
) -> list[dict]:
    """混合检索：向量语义搜索 + 重要性 + 时间衰减

    有 query 时用 embed_text(query) 向量化后，加载该用户所有有 embedding 的
    记忆（LIMIT 200），在 Python 里算余弦相似度排序取 top。
    无 query 时回退到混合评分：score = importance * 0.6 + recencyScore * 0.4
    """
    # ── 语义搜索路径（Python 余弦相似度）──
    if query:
        try:
            vec = embed_text(query)
            with SessionLocal() as db:
                rows = (
                    db.execute(
                        select(UserMemory)
                        .where(
                            UserMemory.userId == user_id,
                            UserMemory.embedding.isnot(None),
                        )
                        .order_by(UserMemory.createdAt.desc())
                        .limit(200)
                    )
                    .scalars()
                    .all()
                )
            if rows:
                # Python 余弦相似度排序
                scored = []
                for r in rows:
                    emb = parse_embedding(r.embedding)
                    sim = cosine_similarity(vec, emb) if emb else 0.0
                    scored.append((r, sim))
                scored.sort(key=lambda item: item[1], reverse=True)
                return [_memory_to_dict(r) for r, _ in scored[:limit]]
            # 向量搜索无结果（所有记忆都还没有 embedding），回退到原逻辑
        except Exception as err:  # noqa: BLE001
            print(f"[Memory] 向量搜索失败，回退到混合评分: {err}")

    # ── 原混合评分路径（无 query 或向量搜索失败）──
    with SessionLocal() as db:
        recent = (
            db.execute(
                select(UserMemory)
                .where(UserMemory.userId == user_id)
                .order_by(UserMemory.createdAt.desc())
                .limit(40)
            )
            .scalars()
            .all()
        )
        important = (
            db.execute(
                select(UserMemory)
                .where(UserMemory.userId == user_id)
                .order_by(UserMemory.importance.desc())
                .limit(10)
            )
            .scalars()
            .all()
        )

    # 去重（按 id）
    seen: set[str] = set()
    pool: list[tuple[UserMemory, float]] = []
    now = _now()
    for m in [*important, *recent]:
        if m.id in seen:
            continue
        seen.add(m.id)

        # 时间衰减 + 综合得分
        recency_score = _recency_score(m.createdAt, now)
        score = (m.importance if m.importance is not None else 0.5) * 0.6 + recency_score * 0.4
        pool.append((m, score))

    # 按得分降序，取 top N
    pool.sort(key=lambda item: item[1], reverse=True)
    return [_memory_to_dict(m) for m, _ in pool[:limit]]


def get_important_memories(user_id: str, limit: int = 10) -> list[dict]:
    """按重要性排序获取记忆（保留，给特定场景用）"""
    with SessionLocal() as db:
        rows = (
            db.execute(
                select(UserMemory)
                .where(UserMemory.userId == user_id)
                .order_by(UserMemory.importance.desc())
                .limit(limit)
            )
            .scalars()
            .all()
        )
    return [_memory_to_dict(m) for m in rows]


def get_memories_by_type(user_id: str, mtype: str, limit: int = 10) -> list[dict]:
    """按类型筛选记忆"""
    with SessionLocal() as db:
        rows = (
            db.execute(
                select(UserMemory)
                .where(UserMemory.userId == user_id, UserMemory.type == mtype)
                .order_by(UserMemory.importance.desc())
                .limit(limit)
            )
            .scalars()
            .all()
        )
    return [_memory_to_dict(m) for m in rows]


def touch_memories(memory_ids: list[str]) -> None:
    """标记记忆被使用（更新 lastUsed）

    当记忆被检索并注入 system prompt 后调用，
    用于记忆生命周期管理 — 长期不用的重要记忆可以重新激活，
    长期不用的低重要性记忆可以被清理。失败不阻断。
    """
    if not memory_ids:
        return
    try:
        with SessionLocal() as db:
            db.execute(
                update(UserMemory)
                .where(UserMemory.id.in_(memory_ids))
                .values(lastUsed=_now())
            )
            db.commit()
    except Exception as err:  # noqa: BLE001
        print(f"[Memory] touchMemories 失败: {err}")


# ---- 格式化 ----

TYPE_LABELS: dict[str, str] = {
    "goal": "🎯 学习目标",
    "weakness": "⚠️ 薄弱环节",
    "skill": "✅ 已有技能",
    "preference": "💡 偏好习惯",
    "habit": "🔄 学习习惯",
    "fact": "📋 其他信息",
}


def format_memories_for_prompt(memories: list[dict]) -> str:
    """将记忆列表格式化为 system prompt 片段（按类型分组，标注重要性）

    :param memories: get_relevant_memories 等返回的 dict 列表
    """
    if not memories:
        return ""

    # 按类型分组
    grouped: dict[str, list[dict]] = {}
    for m in memories:
        key = m.get("type") or "fact"
        grouped.setdefault(key, []).append(m)

    sections: list[str] = []
    for mtype, items in grouped.items():
        label = TYPE_LABELS.get(mtype, mtype)
        lines = []
        for m in items:
            importance = m.get("importance")
            imp = f"[重要度:{round(importance * 100)}%]" if importance is not None else ""
            lines.append(f"  - {imp} {m.get('content', '')}")
        sections.append(f"{label}:\n" + "\n".join(lines))

    return "[关于用户的长期记忆]\n" + "\n\n".join(sections) + "\n"


def format_memories_for_agent(memories: list[dict]) -> str:
    """格式化记忆用于 Agent Runtime 分析（比 prompt 版更简洁）"""
    if not memories:
        return ""

    # 只取最重要的信息
    important = sorted(
        [m for m in memories if (m.get("importance") or 0) >= 0.5],
        key=lambda m: m.get("importance") or 0,
        reverse=True,
    )[:10]

    if not important:
        return ""

    return "\n".join(f"- [{m.get('type')}] {m.get('content', '')}" for m in important)


# ---- 提取与保存 ----

def extract_and_save_memories(user_id: str, conversation: Any) -> None:
    """从一轮对话中提取用户信息，存入数据库。

    设计为 fire-and-forget：调用方不应阻塞主请求。
    提取失败只记日志，不影响对话流。

    实现说明：
    - type 细分：goal/habit/preference/skill/weakness/fact
    - importance + confidence：AI 打分
    - 智能去重：AI 判断匹配到已有记忆（matchExistingId）则更新而不新建

    :param conversation: 对话内容，支持
        {"userMessage": ..., "aiResponse": ...} / {"user": ..., "assistant": ...} /
        {"messages": [{"role", "content"}, ...]} / [{"role", "content"}, ...] / 字符串
    """
    try:
        with SessionLocal() as db:
            rows = (
                db.execute(
                    select(UserMemory)
                    .where(UserMemory.userId == user_id)
                    .order_by(UserMemory.createdAt.desc())
                    .limit(20)
                )
                .scalars()
                .all()
            )
        existing = [{"id": m.id, "content": m.content, "type": m.type} for m in rows]

        extracted = _extract_memories_with_ai(conversation, existing)
        if not extracted:
            print("[Memory] AI 未提取到信息，跳过")
            return

        existing_by_id = {m["id"]: m for m in existing}

        saved = 0
        updated = 0
        for item in extracted:
            match_id = item.get("matchExistingId")
            # AI 标注了匹配的已有记忆 ID → 更新（含 embedding）
            if match_id and match_id in existing_by_id:
                old = existing_by_id[match_id]
                try:
                    with SessionLocal() as db:
                        mem = db.get(UserMemory, match_id)
                        if mem is None:
                            continue
                        # 基础字段更新
                        mem.type = item["type"]
                        mem.content = item["content"]
                        mem.importance = item["importance"]
                        mem.confidence = item["confidence"]
                        mem.lastUsed = _now()
                        db.commit()

                    # 内容变化时重新生成 embedding
                    if old["content"] != item["content"]:
                        try:
                            vec = embed_text(item["content"])
                            with SessionLocal() as db:
                                mem = db.get(UserMemory, match_id)
                                if mem is not None:
                                    mem.embedding = vec
                                    db.commit()
                        except Exception as err:  # noqa: BLE001
                            print(f"[Memory] 更新 embedding 失败: {err}")

                    updated += 1
                    print(
                        f'[Memory] 🔄 语义匹配更新: [{old["type"]}→{item["type"]}] '
                        f'"{old["content"]}" → "{item["content"]}"'
                    )
                except Exception:  # noqa: BLE001
                    pass
                continue

            # AI 没匹配 → 全新创建（含 embedding）
            try:
                vec: Optional[list[float]] = None
                try:
                    vec = embed_text(item["content"])
                except Exception as err:  # noqa: BLE001
                    print(f"[Memory] embedding 生成失败，将不使用向量: {err}")

                with SessionLocal() as db:
                    db.add(
                        UserMemory(
                            userId=user_id,
                            type=item["type"],
                            content=item["content"],
                            embedding=vec,
                            importance=item["importance"],
                            confidence=item["confidence"],
                        )
                    )
                    db.commit()
                saved += 1
                tag = " [向量化]" if vec else ""
                print(f'[Memory] ✨ 新建: [{item["type"]}] "{item["content"]}"{tag}')
            except Exception:  # noqa: BLE001
                pass

        if saved > 0 or updated > 0:
            print(f"[Memory] 用户 {user_id}: 新建 {saved} 条, 更新 {updated} 条")
    except Exception as error:  # noqa: BLE001
        print(f"[Memory] 提取记忆失败: {error}")


# ---- 内部 AI 调用 ----

EXTRACTION_PROMPT = """你是信息提取助手。根据以下对话，提取关于用户的 1-3 条关键信息。

## 提取规则
1. 只提取用户**明确说出**的信息，不要推测
2. 每条用简短中文表述，不超过 30 字，不要加括号注释
3. 如果对话中没有任何用户信息，返回空数组
4. **语义匹配**：参考下方「已有记忆」列表，如果对话信息与某条已有记忆**意思相同**（措辞可以不同），在 matchExistingId 填那条记忆的 ID；如果是新信息填 null

## type 分类
- goal: 学习/职业目标（"准备字节前端面试"、"3个月学完Next.js"）
- weakness: 薄弱环节/困难（"算法题容易卡壳"、"CSS布局不熟"）
- skill: 已有技能/掌握程度（"React熟练"、"TypeScript用了2年"）
- preference: 偏好/倾向（"喜欢边做项目边学"、"早上效率高"）
- habit: 学习习惯/模式（"每天学习2小时"、"周末容易偷懒"）
- fact: 其他事实信息

## importance 评分标准（0.0-1.0）
- 0.9-1.0: 核心目标/关键弱点 — 直接影响学习计划
- 0.7-0.8: 重要偏好/技能 — 影响学习方式
- 0.5-0.6: 一般习惯 — 有参考价值
- 0.3-0.4: 零散事实 — 可能有价值
- 0.1-0.2: 临时信息 — 价值较低

## confidence 评分标准（0.0-1.0）
- 1.0: 用户非常明确地说出
- 0.8: 用户比较明确但未完全展开
- 0.5: 用户简略提及
- 0.3: 不太确定

返回严格 JSON 格式：
[{"content": "...", "type": "goal", "importance": 0.9, "confidence": 1.0, "matchExistingId": "cuid123" | null}]"""


def _split_conversation(conversation: Any) -> tuple[str, str]:
    """把 conversation 归一化为 (用户消息, AI 回复)

    支持形态：
    - dict：{"userMessage": ..., "aiResponse": ...} 或 {"user": ..., "assistant": ...}
    - dict：{"messages": [{"role", "content"}, ...]}
    - list： [{"role": "user"/"assistant", "content": ...}, ...]
            （纯字符串列表则按 user/assistant 交替切分）
    - str：  单条字符串（视为用户消息）
    """
    if isinstance(conversation, str):
        return conversation, ""
    if isinstance(conversation, dict):
        msgs = conversation.get("messages")
        if isinstance(msgs, list) and msgs:
            return _split_conversation(msgs)
        user_msg = conversation.get("userMessage") or conversation.get("user") or ""
        ai_msg = conversation.get("aiResponse") or conversation.get("assistant") or ""
        return str(user_msg), str(ai_msg)
    if isinstance(conversation, (list, tuple)):
        user_parts: list[str] = []
        ai_parts: list[str] = []
        for msg in conversation:
            if isinstance(msg, dict):
                role = str(msg.get("role", "")).lower()
                content = msg.get("content")
                text = str(content) if content is not None else ""
                if role == "user":
                    user_parts.append(text)
                elif role == "assistant":
                    ai_parts.append(text)
            elif isinstance(msg, str):
                # 纯字符串列表：按 user/assistant 交替切分
                (user_parts if len(user_parts) == len(ai_parts) else ai_parts).append(msg)
        return "\n".join(p for p in user_parts if p), "\n".join(p for p in ai_parts if p)
    return str(conversation), ""


def _extract_memories_with_ai(
    conversation: Any,
    existing_memories: list[dict] | None = None,
) -> list[dict]:
    """用 AI 提取记忆（tier="low"，不计入用户 token 精力条）

    解析失败返回空列表，不抛异常。
    返回字段：content / type / importance / confidence / matchExistingId
    """
    existing = existing_memories or []
    existing_list = (
        "\n## 已有记忆（用于语义匹配）\n"
        + "\n".join(f"- id:{m['id']} | {m['content']}" for m in existing)
        if existing
        else ""
    )

    user_msg, ai_msg = _split_conversation(conversation)

    data, _model = completions_with_fallback(
        "low",
        lambda entry, client: client.chat.completions.create(
            model=entry.modelName,
            messages=[
                {"role": "system", "content": EXTRACTION_PROMPT},
                {
                    "role": "user",
                    "content": f"用户说：{user_msg}\n\nAI 回复：{ai_msg}{existing_list}",
                },
            ],
            temperature=0.3,
            max_tokens=500,
            response_format={"type": "json_object"},
        ),
    )

    text = ""
    if getattr(data, "choices", None):
        content = data.choices[0].message.content
        if content:
            text = content.strip()
    if not text:
        return []

    try:
        parsed = json.loads(text)
        items = (
            parsed
            if isinstance(parsed, list)
            else (parsed.get("items") or [] if isinstance(parsed, dict) else [])
        )
        result: list[dict] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            content = item.get("content")
            mtype = item.get("type")
            if not content or not mtype:
                continue
            result.append(
                {
                    "content": content,
                    "type": mtype if isinstance(mtype, str) else "fact",
                    "importance": _clamp_score(item.get("importance", 0.5)),
                    "confidence": _clamp_score(item.get("confidence", 0.5)),
                    "matchExistingId": item.get("matchExistingId") or None,
                }
            )
        return result
    except Exception:  # noqa: BLE001
        print(f"[Memory] AI 提取结果解析失败: {text[:100]}")
        return []


# ---- 冷记忆淘汰 ----

def cleanup_cold_memories(
    user_id: str,
    options: Optional[dict] = None,
) -> dict:
    """淘汰冷记忆

    淘汰规则（按优先级从高到低匹配）：
    ① importance < 0.3 且 lastUsed 超过 30 天  → 删除（不重要且长期未使用）
    ② confidence < 0.3 且 importance < 0.5     → 删除（AI 自己都不确定的低价值信息）
    ③ importance < 0.5 且 lastUsed 超过 60 天  → 删除（中低重要性且长期闲置）
    ④ importance ≥ 0.8                         → 保留（核心目标/关键弱点不淘汰）

    :param options: {"dryRun": bool} 为 True 时只统计不删除
    :return: {"deleted": n, "kept": n, "examined": n}
    """
    dry_run = bool((options or {}).get("dryRun", False))
    now = _now()

    # 获取所有记忆（不做筛选，在应用层判断）
    with SessionLocal() as db:
        all_rows = (
            db.execute(select(UserMemory).where(UserMemory.userId == user_id))
            .scalars()
            .all()
        )

    to_delete: list[str] = []
    reasons: list[str] = []

    for m in all_rows:
        if m.lastUsed:
            days_since_used = int((now - m.lastUsed).total_seconds() // 86400)
        else:
            # 从未用过，按创建时间算
            days_since_used = int((now - m.createdAt).total_seconds() // 86400)

        importance = m.importance if m.importance is not None else 0.5
        confidence = m.confidence if m.confidence is not None else 0.5

        # 规则④：核心目标永远不删
        if importance >= 0.8:
            continue

        # 规则②：AI 自己都不确定的低价值信息
        if confidence < 0.3 and importance < 0.5:
            to_delete.append(m.id)
            reasons.append(f"低置信度({confidence})+低重要性({importance}): {m.type}")
            continue

        # 规则①：不重要 + 30天未使用
        if importance < 0.3 and days_since_used > 30:
            to_delete.append(m.id)
            reasons.append(f"低重要性({importance})+{days_since_used}天未使用: {m.type}")
            continue

        # 规则③：中低重要性 + 60天未使用
        if importance < 0.5 and days_since_used > 60:
            to_delete.append(m.id)
            reasons.append(f"中低重要性({importance})+{days_since_used}天未使用: {m.type}")
            continue

    if not dry_run and to_delete:
        with SessionLocal() as db:
            db.execute(delete(UserMemory).where(UserMemory.id.in_(to_delete)))
            db.commit()

    if to_delete:
        print(
            f"[Memory] {'[DRY RUN] ' if dry_run else ''}淘汰 {len(to_delete)}/{len(all_rows)} 条记忆:\n"
            + "\n".join(f"  - {r}" for r in reasons)
        )

    return {
        "deleted": len(to_delete),
        "kept": len(all_rows) - len(to_delete),
        "examined": len(all_rows),
    }


# ---- 删除 ----

def delete_memory(id: str, user_id: str) -> bool:
    """删除一条记忆（校验归属，非本人返回 False）"""
    with SessionLocal() as db:
        memory = db.get(UserMemory, id)
        if memory is None or memory.userId != user_id:
            return False
        db.delete(memory)
        db.commit()
        return True
