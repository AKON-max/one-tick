# ============================================================
# 工具系统：safeExecute 兜底
# ============================================================

import traceback


def safe_execute(label: str, fn):
    """安全执行，自动捕获异常并返回标准错误格式。

    成功时原样返回 fn() 的结果（不修改结构），
    失败时返回 {'success': False, 'error': str}。
    """
    try:
        return fn()
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        return {"success": False, "error": str(e) or f"{label} 执行失败，请稍后重试"}
