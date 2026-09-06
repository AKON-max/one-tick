"""add garden table (植物农场)

Revision ID: 0002_garden
Revises: 0001_initial
Create Date: 2026-09-06

手动编写（对齐 app/models/garden.py：userId 主键，每用户一行）
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0002_garden"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "garden",
        sa.Column("userId", sa.String(), nullable=False),
        sa.Column("energy", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("wateredCount", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("createdAt", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updatedAt", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["userId"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("userId"),
    )


def downgrade() -> None:
    op.drop_table("garden")
