"""add push_subscriptions table and outbox-hardening columns (Step B1)

Revision ID: d80da57a25c5
Revises: c3f7a2d01e4b
Create Date: 2026-07-13 21:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

import app.database


# revision identifiers, used by Alembic.
revision = 'd80da57a25c5'
down_revision = 'c3f7a2d01e4b'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # B1.2 — push_subscriptions
    op.create_table(
        'push_subscriptions',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('endpoint', sa.String(), nullable=False),
        sa.Column('p256dh', sa.String(), nullable=False),
        sa.Column('auth', sa.String(), nullable=False),
        sa.Column(
            'created_at',
            app.database.UTCDateTime(timezone=True),
            server_default=sa.text('(CURRENT_TIMESTAMP)'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('endpoint'),
    )
    op.create_index(
        'ix_push_subscriptions_user_id', 'push_subscriptions', ['user_id']
    )

    # B1.1 — outbox hardening columns on pending_notifications
    with op.batch_alter_table('pending_notifications', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'next_attempt_at',
                app.database.UTCDateTime(timezone=True),
                server_default=sa.text('(CURRENT_TIMESTAMP)'),
                nullable=False,
            )
        )
        batch_op.add_column(
            sa.Column('dead', sa.Boolean(), server_default=sa.text('0'), nullable=False)
        )
        batch_op.create_index(
            'ix_pending_notifications_dead_next_attempt', ['dead', 'next_attempt_at']
        )

    # B1.1 — notification_log.channel gains 'push'
    with op.batch_alter_table('notification_log', schema=None) as batch_op:
        batch_op.drop_constraint('ck_notification_log_channel', type_='check')
        batch_op.create_check_constraint(
            'ck_notification_log_channel', "channel IN ('email','sms','push')"
        )

    # B1.2 — subscriptions.notify_push
    with op.batch_alter_table('subscriptions', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('notify_push', sa.Boolean(), server_default=sa.text('0'), nullable=False)
        )

    # B1.1 — per-user monthly SMS cap
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('sms_sent_month', sa.Integer(), server_default=sa.text('0'), nullable=False)
        )
        batch_op.add_column(sa.Column('sms_month', sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('sms_month')
        batch_op.drop_column('sms_sent_month')

    with op.batch_alter_table('subscriptions', schema=None) as batch_op:
        batch_op.drop_column('notify_push')

    with op.batch_alter_table('notification_log', schema=None) as batch_op:
        batch_op.drop_constraint('ck_notification_log_channel', type_='check')
        batch_op.create_check_constraint(
            'ck_notification_log_channel', "channel IN ('email','sms')"
        )

    with op.batch_alter_table('pending_notifications', schema=None) as batch_op:
        batch_op.drop_index('ix_pending_notifications_dead_next_attempt')
        batch_op.drop_column('dead')
        batch_op.drop_column('next_attempt_at')

    op.drop_index('ix_push_subscriptions_user_id', table_name='push_subscriptions')
    op.drop_table('push_subscriptions')
