from sqlalchemy import Column, Integer, Float, DateTime
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
