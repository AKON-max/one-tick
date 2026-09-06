"""initial schema: 26 张表全部建表

Revision ID: 0001_initial
Revises:
Create Date: 2026-08-31

手动编写（不用 autogenerate，保证顺序可控：先建 user 再建外键表，再建 pgvector 扩展）
"""
from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 启用 pgvector 扩展（向量检索）──
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # ============================================================
    # 1. user（主根表）
    # ============================================================
    op.create_table(
        "user",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("emailVerified", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("image", sa.String(), nullable=True),
        sa.Column("password", sa.String(), nullable=True),
        sa.Column("bio", sa.String(), nullable=True),
        sa.Column("theme", sa.String(), nullable=False, server_default="system"),
        sa.Column("createdAt", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updatedAt", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )

    # ============================================================
    # 2. session / account（认证）
    # ============================================================
    op.create_table(
        "session",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("userId", sa.String(), nullable=False),
        sa.Column("token", sa.String(), nullable=False),
        sa.Column("expiresAt", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ipAddress", sa.String(), nullable=True),
        sa.Column("userAgent", sa.String(), nullable=True),
        sa.Column("createdAt", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updatedAt", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["userId"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token"),
    )

    op.create_table(
        "account",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("userId", sa.String(), nullable=False),
        sa.Column("providerId", sa.String(), nullable=False),
        sa.Column("accountId", sa.String(), nullable=False),
        sa.Column("provider", sa.String(), nullable=False, server_default="credential"),
        sa.Column("password", sa.String(), nullable=True),
        sa.Column("accessToken", sa.String(), nullable=True),
        sa.Column("refreshToken", sa.String(), nullable=True),
        sa.Column("createdAt", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updatedAt", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["userId"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("providerId", "accountId", name="uq_account_provider_account"),
    )

    # ============================================================
    # 3. plan / plantask / todo / checkin / studyrecord（学习核心）
    # ============================================================
    op.create_table(
        "plan",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("userId", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("goal", sa.String(), nullable=True),
        sa.Column("document", sa.Text(), nullable=True),
        sa.Column("tasksSourceHash", sa.String(), nullable=True),
        sa.Column("tasksSplittingAt", sa.DateTime(timezone=True), nullable=True),
        sa.Column("startDate", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="active"),
        sa.Column("createdAt", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updatedAt", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["userId"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "plantask",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("planId", sa.String(), nullable=False),
        sa.Column("userId", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("dayNumber", sa.Integer(), nullable=True),
        sa.Column("weekNumber", sa.Integer(), nullable=True),
        sa.Column("category", sa.String(), nullable=False, server_default="study"),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("priority", sa.String(), nullable=False, server_default="normal"),
        sa.Column("completedAt", sa.DateTime(timezone=True), nullable=True),
        sa.Column("createdAt", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updatedAt", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["planId"], ["plan.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["userId"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_plantask_planId", "plantask", ["planId"])
    op.create_index("ix_plantask_user_status", "plantask", ["userId", "status"])
    op.create_index("ix_plantask_user_day", "plantask", ["userId", "dayNumber"])

    op.create_table(
        "todo",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("userId", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("completed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("createdAt", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updatedAt", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["userId"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_todo_user_completed", "todo", ["userId", "completed"])
    op.create_index("ix_todo_user_created", "todo", ["userId", "createdAt"])

    op.create_table(
        "checkin",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("userId", sa.String(), nullable=False),
        sa.Column("planId", sa.String(), nullable=True),
        sa.Column("sourceTaskId", sa.String(), nullable=True),
        sa.Column("content", sa.String(), nullable=False),
        sa.Column("hours", sa.Float(), nullable=False, server_default="0"),
        sa.Column("subject", sa.String(), nullable=True),
        sa.Column("mood", sa.String(), nullable=True),
        sa.Column("screenshot", sa.String(), nullable=True),
        sa.Column("checkinDate", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("createdAt", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updatedAt", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["planId"], ["plan.id"]),
        sa.ForeignKeyConstraint(["userId"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_checkin_user_date", "checkin", ["userId", "checkinDate"])
    op.create_index("ix_checkin_source_task", "checkin", ["sourceTaskId"])

    op.create_table(
        "studyrecord",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("userId", sa.String(), nullable=False),
        sa.Column("date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("totalMinutes", sa.Float(), nullable=False, server_default="0"),
        sa.Column("subject", sa.String(), nullable=True),
        sa.Column("checkinId", sa.String(), nullable=True),
        sa.Column("createdAt", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["userId"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_studyrecord_user_date", "studyrecord", ["userId", "date"])

    # ============================================================
    # 4. Agent 相关（run/step/approval/toolcall/decision/schedule/memory/aihistory）
    # ============================================================
    op.create_table(
        "agentrun",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("userId", sa.String(), nullable=False),
        sa.Column("mode", sa.String(), nullable=False, server_default="planner"),
        sa.Column("goal", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="queued"),
        sa.Column("currentStep", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("maxSteps", sa.Integer(), nullable=False, server_default="12"),
        sa.Column("summary", sa.String(), nullable=True),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column("startedAt", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completedAt", sa.DateTime(timezone=True), nullable=True),
        sa.Column("createdAt", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updatedAt", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["userId"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agentrun_user_updated", "agentrun", ["userId", "updatedAt"])
    op.create_index("ix_agentrun_user_status", "agentrun", ["userId", "status"])

    op.create_table(
        "agentstep",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("runId", sa.String(), nullable=False),
        sa.Column("stepNumber", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("detail", sa.String(), nullable=True),
        sa.Column("input", sa.JSON(), nullable=True),
        sa.Column("output", sa.JSON(), nullable=True),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column("startedAt", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completedAt", sa.DateTime(timezone=True), nullable=True),
        sa.Column("createdAt", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["runId"], ["agentrun.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("runId", "stepNumber", name="uq_agentstep_run_step"),
    )
    op.create_index("ix_agentstep_run_status", "agentstep", ["runId", "status"])

    op.create_table(
        "agentapproval",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("runId", sa.String(), nullable=False),
        sa.Column("stepId", sa.String(), nullable=True),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("decisionReason", sa.String(), nullable=True),
        sa.Column("decidedAt", sa.DateTime(timezone=True), nullable=True),
        sa.Column("createdAt", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["runId"], ["agentrun.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["stepId"], ["agentstep.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agentapproval_run_status", "agentapproval", ["runId", "status"])

    op.create_table(
        "agenttoolcall",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("runId", sa.String(), nullable=False),
        sa.Column("stepId", sa.String(), nullable=True),
        sa.Column("toolName", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("idempotencyKey", sa.String(), nullable=True),
        sa.Column("input", sa.JSON(), nullable=True),
        sa.Column("output", sa.JSON(), nullable=True),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column("startedAt", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completedAt", sa.DateTime(timezone=True), nullable=True),
        sa.Column("createdAt", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["runId"], ["agentrun.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["stepId"], ["agentstep.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotencyKey"),
    )
    op.create_index("ix_agenttoolcall_run_status", "agenttoolcall", ["runId", "status"])
    op.create_index("ix_agenttoolcall_run_tool", "agenttoolcall", ["runId", "toolName"])

    op.create_table(
        "agentdecision",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("userId", sa.String(), nullable=False),
        sa.Column("runId", sa.String(), nullable=True),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("reason", sa.String(), nullable=False),
        sa.Column("action", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="executed"),
        sa.Column("feedback", sa.String(), nullable=True),
        sa.Column("createdAt", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["runId"], ["agentrun.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["userId"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agentdecision_user_created", "agentdecision", ["userId", "createdAt"])
    op.create_index("ix_agentdecision_user_type", "agentdecision", ["userId", "type"])
    op.create_index("ix_agentdecision_run", "agentdecision", ["runId"])

    op.create_table(
        "agentschedule",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("userId", sa.String(), nullable=False),
        sa.Column("type", sa.String(), nullable=False, server_default="daily_review"),
        sa.Column("cron", sa.String(), nullable=False, server_default="0 9 * * *"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("lastRunAt", sa.DateTime(timezone=True), nullable=True),
        sa.Column("nextRunAt", sa.DateTime(timezone=True), nullable=True),
        sa.Column("createdAt", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updatedAt", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["userId"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("userId", "type", name="uq_agentschedule_user_type"),
    )
    op.create_index("ix_agentschedule_enabled_next", "agentschedule", ["enabled", "nextRunAt"])

    op.create_table(
        "usermemory",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("userId", sa.String(), nullable=False),
        sa.Column("type", sa.String(), nullable=False, server_default="fact"),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(1024), nullable=True),
        sa.Column("importance", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("lastUsed", sa.DateTime(timezone=True), nullable=True),
        sa.Column("createdAt", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["userId"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_usermemory_user_type", "usermemory", ["userId", "type"])
    op.create_index("ix_usermemory_user_importance", "usermemory", ["userId", "importance"])
    op.create_index("ix_usermemory_user_lastused", "usermemory", ["userId", "lastUsed"])

    op.create_table(
        "aihistory",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("userId", sa.String(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("response", sa.Text(), nullable=False),
        sa.Column("createdAt", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["userId"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_aihistory_user_created", "aihistory", ["userId", "createdAt"])

    # ============================================================
    # 5. 聊天与对话（chatmessage / conversation / conversationmessage）
    # ============================================================
    op.create_table(
        "chatmessage",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("userId", sa.String(), nullable=True),
        sa.Column("role", sa.String(), nullable=False, server_default="user"),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("aiRole", sa.String(), nullable=True),
        sa.Column("createdAt", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["userId"], ["user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_chatmessage_created", "chatmessage", ["createdAt"])

    op.create_table(
        "conversation",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("userId", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False, server_default="新对话"),
        sa.Column("createdAt", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updatedAt", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["userId"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_conversation_user_updated", "conversation", ["userId", "updatedAt"])

    op.create_table(
        "conversationmessage",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("conversationId", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("createdAt", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["conversationId"], ["conversation.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_convmsg_conv_created", "conversationmessage", ["conversationId", "createdAt"])

    # ============================================================
    # 6. 知识库（document / documentchunk / knowledgedoc / plantemplate / documenttemplate）
    # ============================================================
    op.create_table(
        "document",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("userId", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column("createdAt", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updatedAt", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["userId"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_document_user_updated", "document", ["userId", "updatedAt"])

    op.create_table(
        "documentchunk",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("userId", sa.String(), nullable=False),
        sa.Column("sourceName", sa.String(), nullable=False),
        sa.Column("sourceType", sa.String(), nullable=False, server_default="text"),
        sa.Column("chunkIndex", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(1024), nullable=True),
        sa.Column("createdAt", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["userId"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_docchunk_user_source", "documentchunk", ["userId", "sourceName"])
    op.create_index("ix_docchunk_source", "documentchunk", ["sourceName"])

    op.create_table(
        "knowledgedoc",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("userId", sa.String(), nullable=False),
        sa.Column("sourceName", sa.String(), nullable=False),
        sa.Column("sourceType", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("createdAt", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["userId"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("userId", "sourceName", name="uq_knowledgedoc_user_source"),
    )
    op.create_index("ix_knowledgedoc_user", "knowledgedoc", ["userId"])

    op.create_table(
        "plantemplate",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("goal", sa.String(), nullable=True),
        sa.Column("document", sa.Text(), nullable=True),
        sa.Column("createdAt", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "documenttemplate",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column("createdAt", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )

    # ============================================================
    # 7. 杂项（notification / tokenusage / avatarchange）
    # ============================================================
    op.create_table(
        "notification",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("userId", sa.String(), nullable=False),
        sa.Column("type", sa.String(), nullable=False, server_default="reminder"),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("read", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("actionUrl", sa.String(), nullable=True),
        sa.Column("createdAt", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["userId"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_notification_user_read_created", "notification", ["userId", "read", "createdAt"])
    op.create_index("ix_notification_user_type", "notification", ["userId", "type"])

    op.create_table(
        "tokenusage",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("userId", sa.String(), nullable=False),
        sa.Column("surface", sa.String(), nullable=False),
        sa.Column("tier", sa.String(), nullable=False),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("inputTokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("outputTokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("totalTokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("createdAt", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["userId"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tokenusage_user_created", "tokenusage", ["userId", "createdAt"])

    op.create_table(
        "avatarchange",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("userId", sa.String(), nullable=False),
        sa.Column("createdAt", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["userId"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_avatarchange_user_created", "avatarchange", ["userId", "createdAt"])


def downgrade() -> None:
    # 按依赖倒序删除
    op.drop_table("avatarchange")
    op.drop_table("tokenusage")
    op.drop_table("notification")
    op.drop_table("documenttemplate")
    op.drop_table("plantemplate")
    op.drop_table("knowledgedoc")
    op.drop_table("documentchunk")
    op.drop_table("document")
    op.drop_table("conversationmessage")
    op.drop_table("conversation")
    op.drop_table("chatmessage")
    op.drop_table("aihistory")
    op.drop_table("usermemory")
    op.drop_table("agentschedule")
    op.drop_table("agentdecision")
    op.drop_table("agenttoolcall")
    op.drop_table("agentapproval")
    op.drop_table("agentstep")
    op.drop_table("agentrun")
    op.drop_table("studyrecord")
    op.drop_table("checkin")
    op.drop_table("todo")
    op.drop_table("plantask")
    op.drop_table("plan")
    op.drop_table("account")
    op.drop_table("session")
    op.drop_table("user")
    op.execute("DROP EXTENSION IF EXISTS vector")
