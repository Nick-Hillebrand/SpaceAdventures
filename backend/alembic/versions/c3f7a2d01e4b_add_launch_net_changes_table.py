"""add launch_net_changes table

Revision ID: c3f7a2d01e4b
Revises: ba163e7dcc15
Create Date: 2026-07-13 20:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

import app.database


# revision identifiers, used by Alembic.
revision = 'c3f7a2d01e4b'
down_revision = 'ba163e7dcc15'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'launch_net_changes',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('launch_id', sa.String(), nullable=False),
        sa.Column('change_type', sa.String(), nullable=False),
        sa.Column('old_value', sa.String(), nullable=True),
        sa.Column('new_value', sa.String(), nullable=True),
        sa.Column('provider_name', sa.String(), nullable=False),
        sa.Column('rocket_name', sa.String(), nullable=False),
        sa.Column('pad_name', sa.String(), nullable=True),
        sa.Column(
            'detected_at',
            app.database.UTCDateTime(timezone=True),
            server_default=sa.text('(CURRENT_TIMESTAMP)'),
            nullable=False,
        ),
        sa.CheckConstraint(
            "change_type IN ('net', 'status', 'gone')",
            name='ck_launch_net_changes_change_type',
        ),
        sa.ForeignKeyConstraint(
            ['launch_id'],
            ['launches.ll2_id'],
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_launch_net_changes_launch_detected',
        'launch_net_changes',
        ['launch_id', 'detected_at'],
    )
    op.create_index(
        'ix_launch_net_changes_provider_detected',
        'launch_net_changes',
        ['provider_name', 'detected_at'],
    )


def downgrade() -> None:
    op.drop_index('ix_launch_net_changes_provider_detected', table_name='launch_net_changes')
    op.drop_index('ix_launch_net_changes_launch_detected', table_name='launch_net_changes')
    op.drop_table('launch_net_changes')
