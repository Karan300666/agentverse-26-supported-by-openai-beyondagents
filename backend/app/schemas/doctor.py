import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict


class SpecialtyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str


class DoctorRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    specialty: SpecialtyRead
    consultation_fee: int
    currency: str


class AvailabilityRead(BaseModel):
    doctor_id: uuid.UUID
    date: dt.date
    slot_minutes: int
    slots: list[dt.time]