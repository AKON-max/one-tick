# ============================================================
# 模型统一导出（对应 prisma/schema.prisma 的全部 26 张表）
# 按模块组织：
#   base.py     — user / session / account（认证）
#   study.py    — plan / plantask / todo / checkin / studyrecord
#   agent.py    — agentrun / agentstep / agentapproval / agenttoolcall
#                 agentdecision / agentschedule / usermemory / aihistory
#   chat.py     — chatmessage / conversation / conversationmessage
#   knowledge.py— document / documentchunk / knowledgedoc
#                 plantemplate / documenttemplate
#   misc.py     — notification / tokenusage / avatarchange
# ============================================================

from app.models.base import User, Session, Account
from app.models.study import Plan, PlanTask, Todo, Checkin, StudyRecord
from app.models.agent import (
    AgentRun,
    AgentStep,
    AgentApproval,
    AgentToolCall,
    AgentDecision,
    AgentSchedule,
    UserMemory,
    AIHistory,
)
from app.models.chat import ChatMessage, Conversation, ConversationMessage
from app.models.knowledge import (
    Document,
    DocumentChunk,
    KnowledgeDoc,
    PlanTemplate,
    DocumentTemplate,
)
from app.models.misc import Notification, TokenUsage, AvatarChange
from app.models.garden import Garden

__all__ = [
    # base
    "User",
    "Session",
    "Account",
    # study
    "Plan",
    "PlanTask",
    "Todo",
    "Checkin",
    "StudyRecord",
    # agent
    "AgentRun",
    "AgentStep",
    "AgentApproval",
    "AgentToolCall",
    "AgentDecision",
    "AgentSchedule",
    "UserMemory",
    "AIHistory",
    # chat
    "ChatMessage",
    "Conversation",
    "ConversationMessage",
    # knowledge
    "Document",
    "DocumentChunk",
    "KnowledgeDoc",
    "PlanTemplate",
    "DocumentTemplate",
    # misc
    "Notification",
    "TokenUsage",
    "AvatarChange",
    # garden
    "Garden",
]
