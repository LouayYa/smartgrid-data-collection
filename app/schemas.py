from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class ReadingCreate(BaseModel):
    meter_id: int
    timestamp: datetime
    global_active_power: float
    voltage: float
    sub_metering_1: float
    sub_metering_2: float
    sub_metering_3: float


class ReadingResponse(BaseModel):
    reading_id: int
    meter_id: int
    timestamp: datetime
    global_active_power: float
    voltage: float
    sub_metering_1: float
    sub_metering_2: float
    sub_metering_3: float

    model_config = {"from_attributes": True}


class SimulateRequest(BaseModel):
    start_date: Optional[str] = None
    end_date: Optional[str] = None
