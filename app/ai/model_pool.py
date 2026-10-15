# ============================================================
# 模型池（Model Pool）
#
# 背景：每个模型独立免费额度，额度耗尽返回 403（AllocationQuota.FreeTierOnly），
# 需要自动降级到池内下一个模型。model 必须传「完整原始模型字符串」，禁止简写。
#
# 分档：
# - LOW  ：聊天室 / 标题生成 / 记忆提取 / 计划拆分 —— 免费优先，额度用完降级
# - HIGH ：agent / 文档 studio / 后台规划
# - EMBEDDING：知识库 / memory 向量化（不计入用户 token 精力条）
#
# 核心机制：
# ① 进程内记忆已耗尽模型（403 后加入，本进程不再重试）
# ② 临时限流模型（429/rate limit）：冷却 60s 到期后自动恢复
# ③ 记账：成功调用后写 tokenusage；交互式面（enforce）超限抛 UsageLimitError
# ============================================================

import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

from openai import OpenAI

from app.core.config import settings
from app.services.usage import (
    UsageLimitError,
    assert_interactive_usage_allowed,
    record_usage,
)

# ---- 类型 ----

Tier = str  # "low" | "high"


@dataclass
class ModelEntry:
    modelName: str
    displayName: str
    provider: str  # "agnes" | "aliyun"
    modelType: str  # "general" | "embedding" | ...
    tier: Tier
    thinking: bool = False
    freeQuotaEnd: str | None = None


PROVIDER_CONFIG: dict[str, dict] = {
    "agnes": {
        "baseURL": settings.AGNES_BASE_URL,
        "apiKey": settings.AGNES_API_KEY,
    },
    "aliyun": {
        "baseURL": settings.EMBEDDING_BASE_URL if False else "https://dashscope.aliyuncs.com/compatible-mode/v1",
        # 现有项目里 EMBEDDING_API_KEY 就是阿里百炼 key（知识库 embedding 一直在用），可复用
        "apiKey": settings.ALIYUN_API_KEY or settings.EMBEDDING_API_KEY,
    },
}

# ── HIGH 档（agent / 文档 studio / 后台规划）──
HIGH_CHAIN: list[ModelEntry] = [
    ModelEntry("agnes-2.5-flash", "Agnes 2.5 Flash", "agnes", "general", "high"),
    ModelEntry("qwen3.7-max-2026-06-08", "通义千问 3.7 Max", "aliyun", "general", "high", freeQuotaEnd="2026-11-07"),
    ModelEntry("deepseek-v4-pro-0813", "DeepSeek V4 Pro", "aliyun", "general", "high", thinking=True, freeQuotaEnd="2026-11-07"),
    ModelEntry("qwen3-max-2026-01-23", "通义千问 3 Max", "aliyun", "general", "high", freeQuotaEnd="2026-11-07"),
    ModelEntry("qwen3.7-plus-2026-05-26", "通义千问 3.7 Plus", "aliyun", "general", "high", freeQuotaEnd="2026-11-07"),
    ModelEntry("deepseek-v3.2", "DeepSeek V3.2", "aliyun", "general", "high", freeQuotaEnd="2026-11-07"),
    ModelEntry("qwen3.5-plus-2026-04-20", "通义千问 3.5 Plus", "aliyun", "general", "high", freeQuotaEnd="2026-11-07"),
    ModelEntry("qwen-plus-2025-12-01", "通义千问 Plus", "aliyun", "general", "high", freeQuotaEnd="2026-11-07"),
]

# ── LOW 档（聊天室/标题/记忆/拆任务）──
LOW_CHAIN: list[ModelEntry] = [
    ModelEntry("agnes-2.5-flash", "Agnes 2.5 Flash", "agnes", "general", "low"),
    ModelEntry("qwen-flash-2025-07-28", "通义千问 Flash", "aliyun", "general", "low", freeQuotaEnd="2026-11-07"),
    ModelEntry("qwen3.7-flash-2026-07-15", "通义千问 3.7 Flash", "aliyun", "general", "low", freeQuotaEnd="2026-11-07"),
    ModelEntry("qwen3.6-flash", "通义千问 3.6 Flash", "aliyun", "general", "low", freeQuotaEnd="2026-11-07"),
    ModelEntry("qwen-turbo", "通义千问 Turbo", "aliyun", "general", "low", freeQuotaEnd="2026-11-07"),
]

# ── Embedding 档（不计入用户 token 精力条）──
EMBEDDING_CHAIN: list[ModelEntry] = [
    ModelEntry("text-embedding-v4", "通义向量 v4", "aliyun", "embedding", "low", freeQuotaEnd="2026-11-07"),
    ModelEntry("text-embedding-v2", "通义向量 v2", "aliyun", "embedding", "low", freeQuotaEnd="2026-11-07"),
]

# ---- 进程内状态（线程安全）----

_lock = threading.Lock()
_exhausted_models: set[str] = set()
_rate_limited_until: dict[str, float] = {}


def mark_model_exhausted(model_name: str) -> None:
    with _lock:
        _exhausted_models.add(model_name)


def mark_model_rate_limited(model_name: str, cooldown_ms: int = 60_000) -> None:
    with _lock:
        _rate_limited_until[model_name] = time.time() + cooldown_ms / 1000


def is_model_available(name: str) -> bool:
    with _lock:
        if name in _exhausted_models:
            return False
        until = _rate_limited_until.get(name)
        if until is None:
            return True
        if time.time() >= until:
            _rate_limited_until.pop(name, None)  # 冷却结束，恢复
            return True
        return False


# ---- 错误分类 ----

def _match_quota(msg: str) -> bool:
    return (
        "AllocationQuota.FreeTierOnly" in msg
        or "InsufficientBalance" in msg
        or "insufficient_quota" in msg
        or "InsufficientQuota" in msg
        or "quota" in msg.lower()
        or "balance" in msg.lower()
        or "rate limit" in msg.lower()
        or "429" in msg
    )


def is_rate_limit_error(err: Any) -> bool:
    msg = str(err) if not isinstance(err, Exception) else str(err)
    return "429" in msg or "rate limit" in msg.lower()


def is_quota_error(err: Any) -> bool:
    """是否余额/免费额度不足类错误（可降级）；深入嵌套错误检查"""
    msg = str(err)
    if _match_quota(msg):
        return True
    # 嵌套错误（AI SDK 包一层）——OpenAI SDK 的 error body
    body = getattr(err, "body", None)
    if isinstance(body, dict):
        for v in body.values():
            if isinstance(v, str) and _match_quota(v):
                return True
    # openai.BadRequestError 的 response body
    response = getattr(err, "response", None)
    if response is not None:
        try:
            data = response.json()
            if isinstance(data, dict) and "error" in data:
                e = data["error"]
                if isinstance(e, dict):
                    for v in e.values():
                        if isinstance(v, str) and _match_quota(v):
                            return True
        except Exception:  # noqa: BLE001
            pass
    return False


# ---- 客户端构造 ----

def _create_client_for(entry: ModelEntry) -> OpenAI:
    cfg = PROVIDER_CONFIG[entry.provider]
    if not cfg["apiKey"]:
        raise RuntimeError(f"[model-pool] {entry.provider} 未配置 API key")
    # max_retries=0：429/403 直接抛给模型池切下一个模型，SDK 不重试已耗尽/限流的模型
    return OpenAI(api_key=cfg["apiKey"], base_url=cfg["baseURL"], max_retries=0)


def _chain_for(tier: Tier) -> list[ModelEntry]:
    chain = HIGH_CHAIN if tier == "high" else LOW_CHAIN
    return [e for e in chain if is_model_available(e.modelName) and PROVIDER_CONFIG[e.provider]["apiKey"]]


def _embedding_chain() -> list[ModelEntry]:
    return [e for e in EMBEDDING_CHAIN if is_model_available(e.modelName) and PROVIDER_CONFIG[e.provider]["apiKey"]]


def pick_model(tier: Tier) -> ModelEntry:
    chain = _chain_for(tier)
    if not chain:
        raise RuntimeError(f"[model-pool] {tier} 档所有模型均不可用（额度耗尽或未配置 key）")
    return chain[0]


# ---- 用量上下文 ----

class UsageContext:
    def __init__(self, user_id: str, surface: str, enforce: bool = False):
        self.userId = user_id
        self.surface = surface
        self.enforce = enforce


def _usage_field(u: Any, name: str, default: int = 0) -> int:
    """兼容对象（OpenAI 响应）与 dict（流式返回的 usage）两种用法量结构"""
    if isinstance(u, dict):
        return u.get(name, default) or 0
    return getattr(u, name, default) or 0


def _record_usage(entry: ModelEntry, tier: Tier, usage: UsageContext | None, resp: Any) -> None:
    """从 OpenAI 响应里取 usage 并记账（拿不到用量不阻断）。

    resp 可能是 OpenAI 响应对象，也可能是流式调用后返回的 dict（含 usage）。
    """
    if usage is None:
        return
    if isinstance(resp, dict):
        u = resp.get("usage")
    else:
        u = getattr(resp, "usage", None)
    if not u:
        return
    record_usage(
        {
            "userId": usage.userId,
            "surface": usage.surface,
            "tier": tier,
            "model": entry.modelName,
            "inputTokens": _usage_field(u, "prompt_tokens"),
            "outputTokens": _usage_field(u, "completion_tokens"),
            "totalTokens": _usage_field(u, "total_tokens"),
        }
    )


# ---- 向量化（不计入精力条）----

def embedding_with_fallback(input: str | list[str]) -> tuple[list[list[float]], str]:
    """知识库 / memory embedding：按档逐个尝试，额度耗尽自动降级。

    注意：不计入用户 token 精力条 —— 不 recordUsage、不 enforce 每日限额。
    """
    chain = _embedding_chain()
    if not chain:
        raise RuntimeError("[model-pool] embedding 档无可用的模型")
    last_err: Exception | None = None
    for entry in chain:
        try:
            client = _create_client_for(entry)
            res = client.embeddings.create(model=entry.modelName, input=input)
            sorted_data = sorted(res.data, key=lambda d: d.index)
            print(f"[model-pool] embedding 使用 model={entry.modelName} provider={entry.provider}")
            return [item.embedding for item in sorted_data], entry.modelName
        except Exception as err:  # noqa: BLE001
            if is_quota_error(err):
                if is_rate_limit_error(err):
                    mark_model_rate_limited(entry.modelName)
                    print(f"[model-pool] {entry.modelName} 触发限流，冷却 60s 后重试")
                else:
                    mark_model_exhausted(entry.modelName)
                    print(f"[model-pool] {entry.modelName} 免费额度耗尽，降级")
                last_err = err
                continue
            raise
    raise last_err or RuntimeError("[model-pool] embedding 档所有模型请求失败")


# ---- 非流式 completions ----

def completions_with_fallback(
    tier: Tier,
    fn: Callable[[ModelEntry, OpenAI], Any],
    usage: UsageContext | None = None,
) -> tuple[Any, str]:
    """原始 completions：按档逐个尝试，额度耗尽自动降级。

    fn: 接收 (entry, client) 返回响应（含 .usage 供记账）
    """
    chain = _chain_for(tier)
    if not chain:
        raise RuntimeError(f"[model-pool] {tier} 档无可用的模型")
    if usage is not None and usage.enforce:
        assert_interactive_usage_allowed(usage.userId)

    last_err: Exception | None = None
    for entry in chain:
        try:
            client = _create_client_for(entry)
            data = fn(entry, client)
            _record_usage(entry, tier, usage, data)
            print(f"[model-pool] completions 使用 model={entry.modelName} tier={tier}")
            return data, entry.modelName
        except Exception as err:  # noqa: BLE001
            if is_quota_error(err):
                if is_rate_limit_error(err):
                    mark_model_rate_limited(entry.modelName)
                    print(f"[model-pool] {entry.modelName} 触发限流，冷却 60s 后重试")
                else:
                    mark_model_exhausted(entry.modelName)
                    print(f"[model-pool] {entry.modelName} 免费额度耗尽，降级")
                last_err = err
                continue
            raise
    raise last_err or RuntimeError(f"[model-pool] {tier} 档所有模型请求失败")
