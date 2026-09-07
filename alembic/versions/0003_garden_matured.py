"""add garden maturedCount (成熟收获计数)

Revision ID: 0003_garden_matured
Revises: 0002_garden
Create Date: 2026-09-07

手动编写：成熟收获次数，浇水满级后再浇一次 = 收获，小岛树 +1
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0003_garden_matured"
down_revision = "0002_garden"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "garden",
        sa.Column("maturedCount", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("garden", "maturedCount")
