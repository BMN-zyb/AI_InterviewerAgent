"""
FastAPI 应用入口
启动命令：uvicorn api.main:app --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from loguru import logger
import os

from api.middleware import register_middlewares
from api.routers import health, interview, upload, websocket
from config.logging import setup_logger

setup_logger()

app = FastAPI(
    title="InterviewAgent API",
    description="AI 模拟面试官后端接口",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# 注册中间件
register_middlewares(app)

# 注册路由
app.include_router(health.router)
app.include_router(interview.router)
app.include_router(upload.router)
app.include_router(websocket.router)

# 挂载静态文件（CSS / JS）
_static_dir = os.path.join(os.path.dirname(__file__), "..", "frontend", "static")
if os.path.isdir(_static_dir):
    app.mount("/static", StaticFiles(directory=_static_dir), name="static")

# 前端首页
_index_html = os.path.join(os.path.dirname(__file__), "..", "frontend", "index.html")

@app.get("/", include_in_schema=False)
async def serve_index():
    """返回前端首页"""
    if os.path.exists(_index_html):
        return FileResponse(_index_html)
    return {"message": "InterviewAgent API 运行中，访问 /docs 查看接口文档"}


@app.on_event("startup")
async def on_startup():
    logger.info("InterviewAgent API 启动成功")
    logger.info("文档地址: http://0.0.0.0:8000/docs")


@app.on_event("shutdown")
async def on_shutdown():
    logger.info("InterviewAgent API 已关闭")