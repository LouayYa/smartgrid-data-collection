from sqlalchemy import Column, Date, DateTime, Float, Integer, func
from app.database import Base


class Reading(Base):
    __tablename__ = "readings"

    reading_id = Column(Integer, primary_key=True, autoincrement=True)
    meter_id = Column(Integer, nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False)
    global_active_power = Column(Float, nullable=False)
    voltage = Column(Float, nullable=False)
    sub_metering_1 = Column(Float, nullable=False)
    sub_metering_2 = Column(Float, nullable=False)
    sub_metering_3 = Column(Float, nullable=False)


class AnalyticsDaily(Base):
    """Per-meter daily aggregates, computed by the Airflow batch pipeline
    (airflow/dags/daily_consumption_aggregates.py in the umbrella repo)."""

    __tablename__ = "analytics_daily"

    meter_id = Column(Integer, primary_key=True)
    day = Column(Date, primary_key=True)
    avg_power = Column(Float, nullable=False)
    peak_power = Column(Float, nullable=False)
    kitchen_wh = Column(Float, nullable=False)
    laundry_wh = Column(Float, nullable=False)
    water_heater_ac_wh = Column(Float, nullable=False)
    samples = Column(Integer, nullable=False)
    computed_at = Column(DateTime, nullable=False, server_default=func.now())
