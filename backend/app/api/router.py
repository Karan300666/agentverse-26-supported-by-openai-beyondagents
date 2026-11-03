"""Root API router. Feature routers get included here as they are built."""

from fastapi import APIRouter

from app.api.routes import auth

api_router = APIRouter()
api_router.include_router(auth.router)