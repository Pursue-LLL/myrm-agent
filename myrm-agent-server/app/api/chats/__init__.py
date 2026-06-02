"""聊天API模块"""
from fastapi import APIRouter

from .chat import router as chat_router

router = APIRouter()

router.include_router(chat_router)
