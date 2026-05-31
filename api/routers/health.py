"""
健康检查路由
GET /health  -> {"status": "ok", "version": "1.0.0"}
"""
from __future__ import annotations

from fastapi import APIRouter
from api.schemas import HealthResponse

router = APIRouter(tags=["健康检查"])


@router.get("/health", response_model=HealthResponse)
async def health_check():
    return HealthResponse(status="ok", version="1.0.0")