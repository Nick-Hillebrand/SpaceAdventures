"""add rate_limit_events

Revision ID: 6c4989bd3c21
Revises: b3f9a1e0c2d4
Create Date: 2026-07-12 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = '6c4989bd3c21'
down_revision = 'b3f9a1e0c2d4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'rate_limit_events',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('bucket', sa.String(), nullable=False),
        sa.Column('ip_hash', sa.String(), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(),
            nullable=False,
            server_default=sa.text('CURRENT_TIMESTAMP'),
        ),
    )
    op.create_index(
        'ix_rate_limit_events_bucket_ip_created',
        'rate_limit_events',
        ['bucket', 'ip_hash', 'created_at'],
    )


def downgrade() -> None:
    op.drop_index('ix_rate_limit_events_bucket_ip_created', table_name='rate_limit_events')
    op.drop_table('rate_limit_events')
