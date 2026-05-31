"""
FastAPI 中间件：CORS、请求日志、全局异常处理
"""
from __future__ import annotations

import time
import traceback

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger


def register_middlewares(app: FastAPI) -> None:
    """注册所有中间件"""

    # ── CORS ──────────────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],          # 生产环境改为具体域名
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── 请求日志 ──────────────────────────────────────────────────────────────
    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        elapsed = (time.perf_counter() - start) * 1000
        logger.info(
            "{} {} {} {:.1f}ms",
            request.method,
            request.url.path,
            response.status_code,
            elapsed,
        )
        return response

    # ── 全局异常捕获 ──────────────────────────────────────────────────────────
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.error("未捕获异常: {}\n{}", exc, traceback.format_exc())
        return JSONResponse(
            status_code=500,
            content={"error": "内部服务器错误", "detail": str(exc)},
        )