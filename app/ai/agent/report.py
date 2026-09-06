# ============================================================
# Phase 3: 学习报告生成器（对应 src/lib/agent/report.ts）
#
# 报告类型：
# ① generate_daily_report   — 每日学习简报（轻量，主要给用户看）
# ② generate_weekly_report  — 周度学习分析（重量，包含趋势和建议）
#
# 数据来源：
# - Agent Runtime 的 LearningContext（observe 阶段输出）
# - analyzeStudyPattern 的分析结果
# - Agent 的 LLM 分析结果
#
# 设计原则：
# ① 报告是结构化数据（dict/JSON），前端可以渲染为 Markdown 或卡片
# ② 报告可独立存储为 Notification 或单独展示
# ③ 复用已有分析逻辑，不做重复计算
# ============================================================

from datetime import datetime, timezone


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


# ---- 生成每日简报 ----

def generate_daily_report(
    user_id: str,
    context: dict,
    analysis: dict,
    pattern: dict | None = None,
    subject_details: list[dict] | None = None,
    run_id: str | None = None,
) -> dict:
    """生成每日学习简报（对应 generateDailyReport）"""
    today = _now_utc().strftime("%Y-%m-%d")

    # 强弱项：优先用 analyzeStudyPattern 的结果，否则用科目详情兜底
    if pattern and pattern.get("strongSubjects"):
        strengths = list(pattern["strongSubjects"])
    else:
        strengths = [
            d["subject"]
            for d in (subject_details or [])
            if d.get("trend") != "down" and d.get("taskCompletionRate", 0) >= 70
        ]

    if pattern and pattern.get("weakSubjects"):
        weaknesses = list(pattern["weakSubjects"])
    else:
        weaknesses = [
            d["subject"]
            for d in (subject_details or [])
            if d.get("trend") == "down" or d.get("taskCompletionRate", 0) < 50
        ]

    # 建议
    suggestions: list[str] = []
    if pattern and pattern.get("suggestion"):
        suggestions.append(str(pattern["suggestion"]))
    # 从 LLM 分析中提取建议
    for finding in analysis.get("findings", []):
        if finding.get("severity") in ("critical", "warning"):
            suggestions.append(f"⚠️ {finding.get('detail', '')}")
    for action in analysis.get("actions", []):
        if action.get("type") != "ENCOURAGE":
            suggestions.append(f"📋 {action.get('detail', '')}")
    # 去重
    unique_suggestions = list(dict.fromkeys(suggestions))

    return {
        "userId": user_id,
        "date": today,
        "status": analysis.get("status", "on_track"),
        "summary": analysis.get("summary", ""),
        "stats": {
            "streak": context.get("stats", {}).get("streak", 0),
            "completionRate": (pattern or {}).get("completionRate") or 0,
            "todayFocusMinutes": context.get("focus", {}).get("todayMinutes", 0),
            "todayFocusSessions": context.get("focus", {}).get("todaySessions", 0),
        },
        "strengths": strengths[:5],
        "weaknesses": weaknesses[:5],
        "suggestions": unique_suggestions[:5],
        "generatedBy": run_id,
    }


# ---- Markdown 格式化 ----

def format_report_as_markdown(report: dict) -> str:
    """将报告格式化为可读的 Markdown 文本（用于通知或展示）"""
    hour = datetime.now().hour
    if hour < 12:
        greeting = "早上好"
    elif hour < 18:
        greeting = "下午好"
    else:
        greeting = "晚上好"

    lines: list[str] = [
        f"{greeting}，这是你 {report['date']} 的学习小结 ☀️",
        "",
        report.get("summary") or "",
        "",
        f"已经连续打卡 **{report.get('stats', {}).get('streak', 0)} 天**，继续保持！",
        "",
    ]

    stats = report.get("stats", {})
    if stats.get("todayFocusSessions", 0) > 0:
        lines += [
            f"今天完成了 **{stats['todayFocusSessions']} 个番茄钟**，专注了 **{stats['todayFocusMinutes']} 分钟** 🍅",
            "",
        ]

    strengths = report.get("strengths") or []
    if strengths:
        lines += ["做得好的地方："] + [f"- {s}" for s in strengths] + [""]

    weaknesses = report.get("weaknesses") or []
    if weaknesses:
        lines += ["可以多关注一下："] + [f"- {s}" for s in weaknesses] + [""]

    suggestions = report.get("suggestions") or []
    if suggestions:
        lines += ["一些小建议："] + [f"- {s}" for s in suggestions] + [""]

    return "\n".join(lines)


# ---- 生成周度总结 ----

def generate_weekly_report(
    user_id: str,
    context: dict,
    analysis: dict,
    week_start: str,
    week_end: str,
    pattern: dict | None = None,
    subject_details: list[dict] | None = None,
    run_id: str | None = None,
) -> dict:
    """生成周度学习总结（对应 generateWeeklyReport）"""
    daily = generate_daily_report(
        user_id, context, analysis, pattern, subject_details, run_id
    )
    return {
        **daily,
        "date": f"{week_start} ~ {week_end}",
        "weekStart": week_start,
        "weekEnd": week_end,
    }
