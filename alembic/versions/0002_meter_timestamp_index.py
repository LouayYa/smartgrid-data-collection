"""Composite index for the hot query path.

Every analytics call filters readings by meter_id AND a timestamp range
(GET /readings?meter_id=..&start_date=..&end_date=..). A composite
(meter_id, timestamp) index serves that as a single range scan instead
of an index lookup on meter_id followed by a filter.

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-06

"""
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_readings_meter_id_timestamp",
        "readings",
        ["meter_id", "timestamp"],
    )


def downgrade() -> None:
    op.drop_index("ix_readings_meter_id_timestamp", table_name="readings")
