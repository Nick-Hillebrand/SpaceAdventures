"""Add ical_token column to users (L2 iCal feeds).

Revision ID: f1a2b3c4d5e6
Revises: e4a9c1f2b6d7
Create Date: 2026-07-15
"""
from alembic import op
import sqlalchemy as sa

revision = "f1a2b3c4d5e6"
down_revision = "e4a9c1f2b6d7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("ical_token", sa.String(), nullable=True),
    )
    op.create_unique_constraint("uq_users_ical_token", "users", ["ical_token"])


def downgrade() -> None:
    op.drop_constraint("uq_users_ical_token", "users", type_="unique")
    op.drop_column("users", "ical_token")
