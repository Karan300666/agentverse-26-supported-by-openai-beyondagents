"""Root API router. Feature routers get included here as they are built."""

from fastapi import APIRouter

from app.api.routes import appointments, auth, doctors, voice

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(doctors.router)
api_router.include_router(appointments.router)
api_router.include_router(voice.router)