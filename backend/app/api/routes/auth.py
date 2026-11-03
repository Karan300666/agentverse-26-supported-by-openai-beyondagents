from fastapi import APIRouter, HTTPException, status

from app.db.session import DbSession
from app.schemas.patient import PatientCreate, PatientLogin, PatientRead
from app.services import patient_service
from app.services.patient_service import PatientAlreadyExistsError, PatientNotFoundError

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=PatientRead, status_code=status.HTTP_201_CREATED)
async def register(data: PatientCreate, db: DbSession):
    try:
        return await patient_service.register_patient(db, data)
    except PatientAlreadyExistsError:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="Already registered. Please log in as an existing user.",
        ) from None


@router.post("/login", response_model=PatientRead)
async def login(data: PatientLogin, db: DbSession):
    try:
        return await patient_service.login_patient(db, data.phone)
    except PatientNotFoundError:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail="No account found. Please register as a new user.",
        ) from None