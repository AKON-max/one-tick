# ============================================================
# AI 聊天路由
#
# 处理流程：
# ① 鉴权 + 限额早检
# ② 建会话（无则自动创建 + AI 生成标题）
# ③ 保存用户消息
# ④ 上下文截断：只取最近 20 轮（40 条），后端兜底
# ⑤ 长期记忆注入 system prompt + touch
# ⑥ 组装工具（study/rag/todo）→ LLM 工具调用
# ⑦ 流式回复（模型池降级）
# ⑧ onEnd：提取新记忆（fire-and-forget）+ 记账
# ============================================================

import json
import queue
import threading
from typing import Callable, Iterator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.model_pool import (
    completions_with_fallback,
    UsageContext,
)
from app.ai.tools import create_study_tools, create_rag_tool, create_todo_tools, create_agent_tools
from app.ai.memory import (
    get_relevant_memories,
    format_memories_for_prompt,
    touch_memories,
    extract_and_save_memories,
)
from app.core.config import settings
from app.core.security import get_current_user
from app.db.session import SessionLocal, get_db
from app.models.base import User
from app.models.chat import Conversation, ConversationMessage
from app.services.usage import (
    assert_interactive_usage_allowed,
    UsageLimitError,
    ENERGY_DOWN_MESSAGE,
)

router = APIRouter(prefix="/api/ai", tags=["ai"])

MAX_CONTEXT_ROUNDS = 20
MAX_CONTEXT_MESSAGES = MAX_CONTEXT_ROUNDS * 2

SYSTEM_PROMPT = """你不是ai,也不要讨论你是谁研发的，你只是一个助手
你是雨宝，一个贴心的学习伙伴。你像朋友一样跟用户聊天，关心他们的学习状态。

## 说话风格
- 语气自然、简洁，像聊天一样
- 尽量不用 emoji
- 回答尽量精炼，不要啰嗦。能一句话说清的不要写一段
- 用「你」直接跟用户对话，像跟朋友说话
- 专业问题可以讲得深入，但表达要口语化，像朋友在讲解而不是在背书
- 支持 Markdown 渲染

## 输出排版
回答复杂问题时，用结构化 Markdown，不要一大段文字糊在一起：
- 先给结论/要点，再展开细节；内容分块时用 ## 划分小节
- 并列内容用 - 列表；适合对比的信息用 Markdown 表格
- 关键术语、结论、重点用 **加粗**；代码用 ``` 代码块并标注语言
- 段落之间用空行分隔
- 简单问题不强行加标题，保持简短口语化

## 上下文窗口
你的上下文窗口限制为最近 20 轮对话。当用户引用较早的内容但你已无法看到时，可以礼貌说明并请用户补充必要信息。不要凭空编造不在当前上下文中的历史对话内容。

## 长期记忆
系统可能会在下方注入"关于用户的长期记忆"，这些是从你们之前的对话中提取的关键信息。请利用这些记忆提供更个性化的回复。

## 知识库（RAG）
系统可能会在下方注入"知识库检索结果"，这些是从知识库文档中搜索到的与用户问题相关的内容。**重要**：当提示中包含知识库检索结果时，你必须优先基于这些参考资料回答，并在回答中引用来源（如"根据《xxx》..."）。如果搜索结果为空或与问题不相关，可以结合你的知识补充，但要说明知识库中没有找到相关内容。
你可以主动调用 searchKnowledgeBase 工具来搜索知识库。

## 制定学习计划的工作流（重要！）
当用户请你制定学习计划时，你必须遵循以下流程，不要跳过数据收集步骤：
**第一步：收集数据** 调用 getStudyStats 了解用户的学习习惯和当前进度。如果涉及具体方向，也调用 getMyPlans 查看是否有相关计划，调用 getMyMemories 了解用户的偏好和目标。
**第二步：分析差距** 基于数据找出：当前计划的完成情况、任务积压情况、连续打卡状态。在回复中先简要总结你的分析，让用户看到你的建议是基于真实数据的。
**第三步：制定计划** 调用 createPlan 创建计划。只需给出 name、goal、description。详细的阶段文档和每日任务由系统根据你的 goal/description 和学习数据自动生成，你不需要自己写 Markdown 文档。
**注意：createPlan 创建计划后，系统会自动生成学习文档和任务列表，你不需要再调用 breakdownPlanTasks**（重复拆分会造成任务重复）。除非用户明确要求"重新拆分/细化已有计划"。

不要在没有调用 getStudyStats 的情况下直接调用 createPlan（除非用户明确说"直接帮我创建"）。

## 你的能力
- 制定个性化学习计划（基于真实学习数据拆分目标）
- 每日学习检查与进度追踪
- 解答学科问题，用简单语言解释复杂概念
- 分析学习数据，给出改进建议
- 推荐学习方法和资源
- 帮助保持学习动力
- **getStudyStats**：查看学习统计（打卡天数、连续打卡、计划进度、任务完成）
- **createPlan**：创建学习计划
- **getMyPlans**：查询学习计划和进度
- **getRecentCheckins**：查询近期打卡记录
- **getMyMemories**：语义搜索 AI 对你的长期记忆
- **searchKnowledgeBase**：搜索知识库文档
- **getMyTodos**：查看用户的今日待办清单（未完成在前）
- **createTodo**：往今日待办新增一条
- **updateTodo**：勾选/取消某条待办，或修改待办标题
- **deleteTodo**：删除某条待办

## 什么时候用工具
- 用户说"帮我制定学习计划" → getStudyStats → createPlan（创建后系统自动拆分任务，不要再调 breakdownPlanTasks）
- 用户说"分析一下我的学习情况" → getStudyStats + getMyPlans
- 用户说"我有哪些学习计划？" → getMyPlans
- 用户说"我今天学完了吗？/还有什么没做？" → getMyPlans + 相关任务工具
- 用户说"你记得我什么？" → getMyMemories
- 用户问 Agent 开发/AI 编程/技术架构相关问题 → searchKnowledgeBase
- 用户说"我今天有什么待办？/待办清单" → getMyTodos
- 用户说"帮我把X加到今日待办/记一下X" → createTodo
- 用户说"勾掉/取消/改标题/删掉某条待办" → getMyTodos → updateTodo / deleteTodo

## 行为准则
- 始终用中文回复，语气自然像朋友，不要用"作为AI""根据你的请求"这类生硬表述
- 主动追问用户的具体情况，而不是给泛泛的建议
- 回答要有结构性，善用 Markdown 标题和列表，但不要冗长
- 遇到不确定的知识点，诚实说明，不要编造
- 使用工具获取真实数据后再回答，不要凭空编造用户的学习记录
- 用户遇到困难时给予鼓励，但不要空洞地夸奖"""


# ---- DTO ----

class ChatMessageItem(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class AiChatRequest(BaseModel):
    messages: list[ChatMessageItem]
    conversationId: str | None = None
    # 深度思考开关（rainforest-explorer 的 deepThink 开关）
    deepThink: bool = False
    # 文档工作室上下文 { kind, refId, document }（ai-chat-panel 携带当前文档全文）
    studioContext: dict | None = None


class ToolSpec:
    """工具描述（供 LLM 生成参数）"""

    def __init__(self, name: str, description: str, parameters: dict):
        self.name = name
        self.description = description
        self.parameters = parameters

    def to_dict(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


def build_tool_specs(tools: dict) -> list[dict]:
    """把工具执行函数包装成 OpenAI function calling 的 tools 参数"""
    specs = [
        ToolSpec("getStudyStats", "获取用户学习统计（打卡天数、连续打卡、计划进度）。制定计划/分析学情前先调用。", {"type": "object", "properties": {}}),
        ToolSpec("getMyPlans", "查询用户的所有学习计划及完成进度。用户询问计划、查看进度时用。", {"type": "object", "properties": {"status": {"type": "string", "description": "筛选：active/completed，不传查全部"}}}),
        ToolSpec("getRecentCheckins", "查询用户最近的打卡记录（内容、日期）。", {"type": "object", "properties": {"days": {"type": "integer", "description": "最近多少天，默认 7，最大 30"}}}),
        ToolSpec("getMyMemories", "查询 AI 对用户的长期记忆（偏好、目标等）。传 query 按语义搜索，不传返回最重要。", {"type": "object", "properties": {"query": {"type": "string"}, "limit": {"type": "integer"}}}),
        ToolSpec("createPlan", "为用户创建一个新的学习计划。当用户请求制定学习计划、安排学习任务时使用。只需传计划名称、具体目标和一两句说明。", {"type": "object", "properties": {"name": {"type": "string"}, "goal": {"type": "string"}, "description": {"type": "string"}}, "required": ["name"]}),
        ToolSpec("searchKnowledgeBase", "搜索用户个人知识库（其上传的文档/资料）。用户询问自己的文档内容时用。", {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}),
        ToolSpec("getMyTodos", "查询用户当前的今日待办清单（未完成在前）。用户问'我今天有什么待办/待办清单/还剩哪些待办'时用。", {"type": "object", "properties": {}}),
        ToolSpec("createTodo", "新增一条今日待办。用户说'帮我把X加入待办/记一下X/今天要做X'时用。", {"type": "object", "properties": {"title": {"type": "string"}}, "required": ["title"]}),
        ToolSpec("updateTodo", "更新一条今日待办：勾选完成/取消，或修改标题。先通过 getMyTodos 拿到待办 id。", {"type": "object", "properties": {"id": {"type": "string"}, "title": {"type": "string"}, "completed": {"type": "boolean"}}, "required": ["id"]}),
        ToolSpec("deleteTodo", "删除一条今日待办。先通过 getMyTodos 拿到待办 id。", {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]}),
        ToolSpec("breakdownPlanTasks", "把学习计划拆分为平铺的具体可执行任务。拆分前先通过 getMyPlans 拿到 planId。任务要具体、可量化、有完成标准；不要按周/天分组。", {"type": "object", "properties": {"planId": {"type": "string"}}, "required": ["planId"]}),
        ToolSpec("getPlanTasks", "查询某个计划的所有任务及完成进度。用户问'我的计划进度/任务完成情况'时用。", {"type": "object", "properties": {"planId": {"type": "string"}}, "required": ["planId"]}),
        ToolSpec("updateTaskStatus", "更新任务状态（pending/in_progress/done/skipped）。用户报告完成任务时用。", {"type": "object", "properties": {"taskId": {"type": "string"}, "status": {"type": "string"}}, "required": ["taskId", "status"]}),
        ToolSpec("getTodayTasks", "获取今日应完成的任务清单。用户说'今天学什么/今日任务/检查进度'时用。", {"type": "object", "properties": {}}),
    ]
    # 只返回实际存在的工具
    return [s.to_dict() for s in specs if s.name in tools]


def generate_chat_title(first_message: str, user_id: str | None = None) -> str:
    """用 AI 根据首条消息自动生成对话标题（失败回落首条消息前 20 字）"""
    try:
        data, _model = completions_with_fallback(
            "low",
            lambda entry, client: client.chat.completions.create(
                model=entry.modelName,
                messages=[
                    {
                        "role": "system",
                        "content": "根据用户消息生成对话标题，不要有额外的说明或解释，要抓住核心信息不要什么都总结，不超过15字，只输出标题本身。",
                    },
                    {"role": "user", "content": first_message},
                ],
                temperature=0.5,
            ),
            UsageContext(user_id, "title") if user_id else None,
        )
        title = data.choices[0].message.content.strip() if data.choices else ""
        return title or first_message[:20]
    except Exception as e:  # noqa: BLE001
        print(f"[generateChatTitle] 失败，回落默认标题: {e}")
        return first_message[:20]


def _execute_tool_call(tools: dict, name: str, args: dict) -> dict:
    """执行 LLM 请求的工具调用"""
    tool = tools.get(name)
    if tool is None:
        return {"success": False, "error": f"未知工具: {name}"}
    try:
        parsed = json.loads(args) if isinstance(args, str) else args
    except json.JSONDecodeError:
        parsed = {}
    return tool(parsed if isinstance(parsed, dict) else {})


def _run_agent_loop(
    client,
    model_name: str,
    messages: list[dict],
    tools: dict,
    tool_specs: list[dict],
    max_rounds: int = 4,
    on_delta: Callable[[str], None] | None = None,
):
    """简易 Agent 循环：LLM 判断 → 调用工具 → 观察结果 → 再判断。

    基于 maxSteps 与 Tool Calling 的受限工具循环。
    每一轮都用 stream=True 流式调用：
    - content delta 立即通过 on_delta 吐出（前端打字机效果）
    - 同时累积 tool_calls 判断是否要执行工具
    返回 dict：content / messages / usage（供记账）。
    """
    current_messages = list(messages)
    tool_messages: list[dict] = []

    def _stream_round(msgs: list[dict]) -> dict:
        """流式跑一轮，返回 {content, tool_calls, usage}"""
        parts: list[str] = []
        tool_calls_by_index: dict[int, dict] = {}
        usage = None
        stream = client.chat.completions.create(
            model=model_name,
            messages=msgs,
            tools=tool_specs,
            tool_choice="auto",
            stream=True,
            stream_options={"include_usage": True},
        )
        for chunk in stream:
            if chunk.usage:
                usage = chunk.usage
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta.content:
                parts.append(delta.content)
                if on_delta:
                    on_delta(delta.content)
            if delta.tool_calls:
                for tc in delta.tool_calls:
                    entry = tool_calls_by_index.setdefault(tc.index, {"id": "", "name": "", "arguments": ""})
                    if tc.id:
                        entry["id"] = tc.id
                    if tc.function:
                        if tc.function.name:
                            entry["name"] += tc.function.name
                        if tc.function.arguments:
                            entry["arguments"] += tc.function.arguments
        return {
            "content": "".join(parts),
            "tool_calls": [tool_calls_by_index[i] for i in sorted(tool_calls_by_index)],
            "usage": usage,
        }

    for _round in range(max_rounds):
        round_data = _stream_round(current_messages)
        parts = round_data["tool_calls"]

        if not parts:
            # 无工具调用：流式内容即最终回复
            return {
                "content": round_data["content"],
                "messages": current_messages,
                "usage": round_data["usage"],
            }

        # 有工具调用：执行并追加结果，继续下一轮
        tool_messages = []
        for tc in parts:
            result = _execute_tool_call(tools, tc["name"], tc["arguments"])
            print(f"[AgentLoop] 调用工具 {tc['name']} → {str(result)[:120]}")
            tool_messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": json.dumps(result, ensure_ascii=False),
                }
            )
        current_messages.append(
            {
                "role": "assistant",
                "content": round_data["content"],
                "tool_calls": [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {"name": tc["name"], "arguments": tc["arguments"]},
                    }
                    for tc in parts
                ],
            }
        )
        current_messages.extend(tool_messages)

    # 达到轮次上限，做最后一次无工具调用（仍流式）
    final_messages = [m for m in current_messages if m.get("role") != "tool"]
    round_data = _stream_round(final_messages)
    return {
        "content": round_data["content"],
        "messages": final_messages,
        "usage": round_data["usage"],
    }


@router.post("")
@router.post("/chat")
async def ai_chat(
    req: AiChatRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """AI 聊天（流式回复 + 工具调用 + 记忆注入）"""
    # ① 限额早检（交互式面）
    try:
        assert_interactive_usage_allowed(user.id, db)
    except UsageLimitError:
        return {"content": ENERGY_DOWN_MESSAGE}

    if not req.messages:
        raise HTTPException(status_code=400, detail="Messages are required")

    # ② 会话创建 + AI 标题
    conversation_id = req.conversationId
    if not conversation_id:
        last_user_msg = req.messages[-1].content
        title = generate_chat_title(last_user_msg, user.id)
        conv = Conversation(userId=user.id, title=title)
        db.add(conv)
        db.commit()
        db.refresh(conv)
        conversation_id = conv.id
    else:
        conv = db.get(Conversation, conversation_id)
        if conv is None or conv.userId != user.id:
            raise HTTPException(status_code=404, detail="会话不存在")

    # ③ 保存用户消息
    last_user_msg = req.messages[-1].content
    db.add(
        ConversationMessage(
            conversationId=conversation_id,
            role="user",
            content=last_user_msg,
        )
    )
    db.commit()

    # ④ 上下文截断（后端兜底：最近 20 轮 / 40 条）
    messages = [{"role": m.role, "content": m.content} for m in req.messages]
    if len(messages) > MAX_CONTEXT_MESSAGES:
        messages = messages[-MAX_CONTEXT_MESSAGES:]
        print(f"[AI] 后端截断: {len(req.messages)} → {MAX_CONTEXT_MESSAGES} 条消息")

    # ⑤ 长期记忆注入
    memory_prompt = ""
    try:
        memories = get_relevant_memories(user.id)
        memory_prompt = format_memories_for_prompt(memories)
        if memories:
            touch_memories([m["id"] for m in memories])
    except Exception as e:  # noqa: BLE001
        print(f"[AI] 记忆注入失败: {e}")

    system_content = SYSTEM_PROMPT
    if memory_prompt:
        system_content += f"\n\n## 关于用户的长期记忆\n{memory_prompt}"

    # 文档工作室上下文：注入用户正在编辑的文档全文（studioContext.document），
    # 让 AI 的回复围绕当前文档展开（可直接给出修改建议文本）
    studio = req.studioContext or {}
    doc_text = (studio.get("document") or "").strip()
    if doc_text:
        kind = studio.get("kind") or "文档"
        system_content += (
            f"\n\n## 当前{kind}内容（用户正在编辑，你的回答应围绕它）\n"
            f"<document>\n{doc_text[:8000]}\n</document>"
        )

    # 深度思考：提示模型先梳理再作答（rainforest 的 deepThink 开关）
    if req.deepThink:
        system_content += (
            "\n\n用户开启了深度思考模式：先在心里理清逻辑与依据，"
            "再给出更完整、更有深度的分析。"
        )

    # ⑥ 组装工具
    tools = {}
    tools.update(create_study_tools(user.id))
    tools.update(create_rag_tool(user.id))
    tools.update(create_todo_tools(user.id))
    tools.update(create_agent_tools(user.id))
    tool_specs = build_tool_specs(tools)

    full_messages = [{"role": "system", "content": system_content}] + messages

    # ⑦ 真流式回复：模型池降级；线程内跑 Agent 循环，LLM 的每个增量 token
    #    经队列实时推到响应流（on_delta → queue → yield），前端即打即显。
    def stream_generator() -> Iterator[str]:
        q: queue.Queue = queue.Queue()
        state: dict = {"error": None, "content": None}

        def on_delta(delta: str) -> None:
            q.put(delta)

        def work() -> None:
            try:
                data, _model_name = completions_with_fallback(
                    "high",
                    lambda entry, client: _run_agent_loop(
                        client,
                        entry.modelName,
                        full_messages,
                        tools,
                        tool_specs,
                        on_delta=on_delta,
                    ),
                    UsageContext(user.id, "agent", enforce=True),
                )
                state["content"] = (data or {}).get("content") or ""
            except UsageLimitError:
                state["error"] = "limit"
            except Exception as e:  # noqa: BLE001
                print(f"[AI] 调用失败: {e}")
                state["error"] = "generic"
            finally:
                q.put(None)

        threading.Thread(target=work, daemon=True).start()

        # 流式转发：LLM 生成一个增量，这里就吐一个
        while True:
            item = q.get()
            if item is None:
                break
            if item:
                yield item

        if state["error"] == "limit":
            yield ENERGY_DOWN_MESSAGE
            return
        if state["error"]:
            yield "（抱歉，我刚才走神了，请再试一次）"
            return

        content = state["content"] or ""
        if not content:
            return

        # ⑧ 保存 AI 回复（独立会话，避免跨线程复用路由注入的 db）
        try:
            with SessionLocal() as db2:
                db2.add(
                    ConversationMessage(
                        conversationId=conversation_id,
                        role="assistant",
                        content=content,
                    )
                )
                db2.commit()
        except Exception as e:  # noqa: BLE001
            print(f"[AI] 落库失败: {e}")

        # 提取新记忆（fire-and-forget，不阻塞主流程）
        try:
            extract_and_save_memories(
                user.id,
                {"userMessage": last_user_msg, "aiResponse": content},
            )
        except Exception as e:  # noqa: BLE001
            print(f"[AI] 记忆提取失败: {e}")

    return StreamingResponse(
        stream_generator(),
        media_type="text/plain; charset=utf-8",
        headers={"X-Conversation-Id": conversation_id},
    )
