"""Media gallery API routes."""

from fastapi import APIRouter

from app.api.media.batch_routes import router as batch_router
from app.api.media.router import router as gallery_router

media_router = APIRouter()
media_router.include_router(gallery_router)
media_router.include_router(batch_router, prefix="/batch")

__all__ = ["media_router"]
