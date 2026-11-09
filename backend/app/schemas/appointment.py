import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict

from app.schemas.doctor import DoctorRead


class AppointmentBook(BaseModel):
    doctor_id: uuid.UUID
    appointment_date: dt.date
    start_time: dt.time


class AppointmentReschedule(BaseModel):
    appointment_date: dt.date
    start_time: dt.time


class AppointmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    doctor: DoctorRead
    appointment_date: dt.date
    start_time: dt.time
    status: str
    fee_amount: int