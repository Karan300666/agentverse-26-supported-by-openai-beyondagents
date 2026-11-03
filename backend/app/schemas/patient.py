import uuid
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Phone = Annotated[str, StringConstraints(pattern=r"^[0-9]{10}$")]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class PatientCreate(BaseModel):
    name: Name
    age: int = Field(ge=0, le=120)
    phone: Phone


class PatientLogin(BaseModel):
    phone: Phone


class PatientRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    age: int
    phone: str