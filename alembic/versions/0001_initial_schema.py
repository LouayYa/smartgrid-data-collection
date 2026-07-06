"""Initial schema — the readings table.

Databases that predate Alembic already have this table from
Base.metadata.create_all(), so the upgrade is a no-op when it exists —
that adopts the live schema without touching data.

Revision ID: 0001
Revises:
Create Date: 2026-07-06

"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

TABLE = "readings"


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table(TABLE):
        return

    op.create_table(
        TABLE,
        sa.Column("reading_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("meter_id", sa.Integer(), nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("global_active_power", sa.Float(), nullable=False),
        sa.Column("voltage", sa.Float(), nullable=False),
        sa.Column("sub_metering_1", sa.Float(), nullable=False),
        sa.Column("sub_metering_2", sa.Float(), nullable=False),
        sa.Column("sub_metering_3", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("reading_id"),
    )
    op.create_index(op.f("ix_readings_meter_id"), TABLE, ["meter_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_readings_meter_id"), table_name=TABLE)
    op.drop_table(TABLE)
