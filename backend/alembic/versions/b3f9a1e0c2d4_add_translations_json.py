"""add translations_json to apod and launches

Revision ID: b3f9a1e0c2d4
Revises: ee08ba069158
Create Date: 2026-07-06 14:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'b3f9a1e0c2d4'
down_revision = 'ee08ba069158'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('apod', schema=None) as batch_op:
        batch_op.add_column(sa.Column('translations_json', sa.String(), nullable=True))

    with op.batch_alter_table('launches', schema=None) as batch_op:
        batch_op.add_column(sa.Column('translations_json', sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('launches', schema=None) as batch_op:
        batch_op.drop_column('translations_json')

    with op.batch_alter_table('apod', schema=None) as batch_op:
        batch_op.drop_column('translations_json')
