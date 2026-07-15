"""add tracked_objects and ephemerides tables

Revision ID: 9cd57e6874ae
Revises: d80da57a25c5
Create Date: 2026-07-14 12:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

import app.database


# revision identifiers, used by Alembic.
revision = '9cd57e6874ae'
down_revision = 'd80da57a25c5'
branch_labels = None
depends_on = None

# Seed set (22-ephemeris-and-mission-replay.md — Foundation): adding an
# object is one row, no code change.
_SEED_OBJECTS = [
    ('-170', 'jwst', 'spacecraft.jwst', 'spacecraft'),
    ('-31', 'voyager-1', 'spacecraft.voyager1', 'spacecraft'),
    ('-32', 'voyager-2', 'spacecraft.voyager2', 'spacecraft'),
    ('-96', 'parker-solar-probe', 'spacecraft.parkerSolarProbe', 'spacecraft'),
    ('-98', 'new-horizons', 'spacecraft.newHorizons', 'spacecraft'),
]


def upgrade() -> None:
    tracked_objects = op.create_table(
        'tracked_objects',
        sa.Column('spk_id', sa.String(), nullable=False),
        sa.Column('slug', sa.String(), nullable=False),
        sa.Column('name_key', sa.String(), nullable=False),
        sa.Column('kind', sa.String(), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=False),
        sa.Column('step_hours', sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "kind IN ('spacecraft', 'small_body')",
            name='ck_tracked_objects_kind',
        ),
        sa.PrimaryKeyConstraint('spk_id'),
        sa.UniqueConstraint('slug'),
    )
    op.create_table(
        'ephemerides',
        sa.Column('spk_id', sa.String(), nullable=False),
        sa.Column(
            't_utc',
            app.database.UTCDateTime(timezone=True),
            nullable=False,
        ),
        sa.Column('x_au', sa.Float(), nullable=False),
        sa.Column('y_au', sa.Float(), nullable=False),
        sa.Column('z_au', sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(
            ['spk_id'],
            ['tracked_objects.spk_id'],
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('spk_id', 't_utc'),
    )

    op.bulk_insert(
        tracked_objects,
        [
            {
                'spk_id': spk_id,
                'slug': slug,
                'name_key': name_key,
                'kind': kind,
                'active': True,
                'step_hours': 24,
            }
            for spk_id, slug, name_key, kind in _SEED_OBJECTS
        ],
    )


def downgrade() -> None:
    op.drop_table('ephemerides')
    op.drop_table('tracked_objects')
