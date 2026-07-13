"""notification_log.user_id nullable (P1.10 anonymize-on-delete)

Revision ID: 9a2c1e5f7b3d
Revises: 7fbb4f4786fa
Create Date: 2026-07-13 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = '9a2c1e5f7b3d'
down_revision = '7fbb4f4786fa'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('notification_log') as batch_op:
        batch_op.alter_column('user_id', existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    with op.batch_alter_table('notification_log') as batch_op:
        batch_op.alter_column('user_id', existing_type=sa.Integer(), nullable=False)
