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
    # batch mode — SQLite (dev) cannot ALTER constraints in place; on
    # Postgres this compiles to plain ALTER TABLE statements.
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(sa.Column("ical_token", sa.String(), nullable=True))
        batch_op.create_unique_constraint("uq_users_ical_token", ["ical_token"])


def downgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_constraint("uq_users_ical_token", type_="unique")
        batch_op.drop_column("ical_token")
