"""add location/pro columns and iss_pass_alerts table (Step L1)

Revision ID: e4a9c1f2b6d7
Revises: d80da57a25c5
Create Date: 2026-07-15 09:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

import app.database


# revision identifiers, used by Alembic.
revision = 'e4a9c1f2b6d7'
down_revision = 'd80da57a25c5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # L1 foundation — sky-alert location + Pro flagship gating
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('location_name', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('location_lat', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('location_lng', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('location_tz', sa.String(), nullable=True))
        batch_op.add_column(
            sa.Column('is_pro', sa.Boolean(), server_default=sa.text('0'), nullable=False)
        )

    # L1 — precomputed per-user ISS visual pass alerts. Named
    # `iss_pass_alerts`, not the spec's literal `iss_passes` — that name is
    # already taken by the pre-existing generic pass cache table.
    op.create_table(
        'iss_pass_alerts',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('start_utc', app.database.UTCDateTime(timezone=True), nullable=False),
        sa.Column('end_utc', app.database.UTCDateTime(timezone=True), nullable=False),
        sa.Column('max_el', sa.Float(), nullable=False),
        sa.Column('start_az', sa.Float(), nullable=False),
        sa.Column('end_az', sa.Float(), nullable=False),
        sa.Column('mag', sa.Float(), nullable=True),
        sa.Column('notified', sa.Boolean(), server_default=sa.text('0'), nullable=False),
        sa.Column(
            'fetched_at',
            app.database.UTCDateTime(timezone=True),
            server_default=sa.text('(CURRENT_TIMESTAMP)'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'start_utc', name='uq_iss_pass_alerts_user_start'),
    )
    op.create_index(
        'ix_iss_pass_alerts_notified_start', 'iss_pass_alerts', ['notified', 'start_utc']
    )

    # L1 — subscriptions.type gains 'iss_pass'
    with op.batch_alter_table('subscriptions', schema=None) as batch_op:
        batch_op.drop_constraint('ck_subscription_type', type_='check')
        batch_op.create_check_constraint(
            'ck_subscription_type', "type IN ('launch','agency','iss_pass')"
        )

    # ll2_id/agency_name are both NULL for type='iss_pass', so the existing
    # per-type UniqueConstraints don't stop a second row for the same user —
    # this partial index enforces "one iss_pass subscription per user".
    op.create_index(
        'uq_subscriptions_iss_pass_user',
        'subscriptions',
        ['user_id'],
        unique=True,
        sqlite_where=sa.text("type = 'iss_pass'"),
        postgresql_where=sa.text("type = 'iss_pass'"),
    )

    # L1 — outbox extended to carry ISS pass alerts alongside launch updates
    with op.batch_alter_table('pending_notifications', schema=None) as batch_op:
        batch_op.alter_column('ll2_id', existing_type=sa.String(), nullable=True)
        batch_op.add_column(sa.Column('iss_pass_alert_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_pending_notifications_iss_pass_alert_id',
            'iss_pass_alerts',
            ['iss_pass_alert_id'],
            ['id'],
            ondelete='CASCADE',
        )
        batch_op.drop_constraint('ck_pending_notifications_change_type', type_='check')
        batch_op.create_check_constraint(
            'ck_pending_notifications_change_type',
            "change_type IN ('NET_SLIP','STATUS_CHANGE','NEW_LAUNCH','ISS_PASS')",
        )

    with op.batch_alter_table('notification_log', schema=None) as batch_op:
        batch_op.alter_column('ll2_id', existing_type=sa.String(), nullable=True)
        batch_op.add_column(sa.Column('iss_pass_alert_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_notification_log_iss_pass_alert_id',
            'iss_pass_alerts',
            ['iss_pass_alert_id'],
            ['id'],
            ondelete='SET NULL',
        )


def downgrade() -> None:
    with op.batch_alter_table('notification_log', schema=None) as batch_op:
        batch_op.drop_constraint('fk_notification_log_iss_pass_alert_id', type_='foreignkey')
        batch_op.drop_column('iss_pass_alert_id')
        batch_op.alter_column('ll2_id', existing_type=sa.String(), nullable=False)

    with op.batch_alter_table('pending_notifications', schema=None) as batch_op:
        batch_op.drop_constraint('ck_pending_notifications_change_type', type_='check')
        batch_op.create_check_constraint(
            'ck_pending_notifications_change_type',
            "change_type IN ('NET_SLIP','STATUS_CHANGE','NEW_LAUNCH')",
        )
        batch_op.drop_constraint('fk_pending_notifications_iss_pass_alert_id', type_='foreignkey')
        batch_op.drop_column('iss_pass_alert_id')
        batch_op.alter_column('ll2_id', existing_type=sa.String(), nullable=False)

    with op.batch_alter_table('subscriptions', schema=None) as batch_op:
        batch_op.drop_constraint('ck_subscription_type', type_='check')
        batch_op.create_check_constraint(
            'ck_subscription_type', "type IN ('launch','agency')"
        )

    op.drop_index('uq_subscriptions_iss_pass_user', table_name='subscriptions')
    op.drop_index('ix_iss_pass_alerts_notified_start', table_name='iss_pass_alerts')
    op.drop_table('iss_pass_alerts')

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('is_pro')
        batch_op.drop_column('location_tz')
        batch_op.drop_column('location_lng')
        batch_op.drop_column('location_lat')
        batch_op.drop_column('location_name')
