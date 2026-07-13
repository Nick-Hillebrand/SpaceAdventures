"""add user consent columns

Revision ID: 7fbb4f4786fa
Revises: 6c4989bd3c21
Create Date: 2026-07-12 00:30:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = '7fbb4f4786fa'
down_revision = '6c4989bd3c21'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('users') as batch_op:
        batch_op.add_column(sa.Column('consent_notifications_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('consent_source', sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('users') as batch_op:
        batch_op.drop_column('consent_source')
        batch_op.drop_column('consent_notifications_at')
