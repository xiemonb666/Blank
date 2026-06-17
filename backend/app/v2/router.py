from __future__ import annotations

from fastapi import APIRouter

from .chat import router as chat_router

# V2 API 总路由，所有子模块路由统一挂载在此
v2_router = APIRouter(prefix="/api/v2")

# 注册子路由
v2_router.include_router(chat_router)
