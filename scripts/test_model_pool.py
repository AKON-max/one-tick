# 测试模型池 + 用量记账（临时脚本）
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

print("=== 测试用量记账 ===")
from app.services.usage import record_usage, get_today_usage, UsageLimitError, assert_interactive_usage_allowed

# 记账（无 AI 调用，直接写库）
record_usage({
    "userId": "e80d9aa9b13245419c706f6c4f06f65c",
    "surface": "test",
    "tier": "low",
    "model": "test-model",
    "inputTokens": 100,
    "outputTokens": 50,
    "totalTokens": 150,
})
data = get_today_usage("e80d9aa9b13245419c706f6c4f06f65c")
print(f"用量: used={data['used']}, limit={data['limit']}, remaining={data['remaining']}, unlimited={data['unlimited']}")
assert data["used"] >= 150, "用量记录失败"
print("✅ 用量记账 OK")

print("\n=== 测试模型池 ===")
from app.ai.model_pool import _chain_for, _embedding_chain, pick_model, is_quota_error, mark_model_exhausted

# 无 API key 时应返回空链或抛错
chain = _chain_for("low")
print(f"LOW 档可用链: {len(chain)} 个 (当前无 key 配置)")

# 错误分类测试
class FakeErr(Exception):
    pass

err1 = FakeErr("Error code: 403 - AllocationQuota.FreeTierOnly exceeded")
print(f"403 配额错误识别: {is_quota_error(err1)}")
assert is_quota_error(err1), "403 配额应识别为可降级错误"

err2 = FakeErr("HTTP 429 Too Many Requests - rate limit")
print(f"429 限流识别: {is_quota_error(err2)}, rate_limit: {is_quota_error(err2)}")
assert is_quota_error(err2), "429 应识别"

err3 = FakeErr("connection timeout")
print(f"网络错误识别: {is_quota_error(err3)}")
assert not is_quota_error(err3), "网络错误不应触发降级"

print("\n=== 全部测试通过 ===")
