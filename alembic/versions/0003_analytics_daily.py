"""analytics_daily — per-meter daily aggregates written by Airflow.

The daily_consumption_aggregates DAG upserts into this table; the API
serves it via GET /aggregates/daily. Composite PK (meter_id, day) makes
the batch upsert idempotent.

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-06

"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "analytics_daily",
        sa.Column("meter_id", sa.Integer(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("avg_power", sa.Float(), nullable=False),
        sa.Column("peak_power", sa.Float(), nullable=False),
        sa.Column("kitchen_wh", sa.Float(), nullable=False),
        sa.Column("laundry_wh", sa.Float(), nullable=False),
        sa.Column("water_heater_ac_wh", sa.Float(), nullable=False),
        sa.Column("samples", sa.Integer(), nullable=False),
        sa.Column("computed_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("meter_id", "day"),
    )


def downgrade() -> None:
    op.drop_table("analytics_daily")
