"""
日志配置：基于 loguru，统一输出格式，自动轮转
"""
import sys
from pathlib import Path

from loguru import logger

from config.settings import settings

LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

_configured = False


def setup_logger() -> None:
    """初始化全局 loguru logger（只配置一次）"""
    global _configured
    if _configured:
        return

    logger.remove()  # 移除默认 handler

    # 控制台
    logger.add(
        sys.stderr,
        level=settings.log_level,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
            "<level>{message}</level>"
        ),
        colorize=True,
    )

    # 文件：每天轮转，保留 30 天
    logger.add(
        LOG_DIR / "interview_agent_{time:YYYY-MM-DD}.log",
        rotation="00:00",
        retention="30 days",
        encoding="utf-8",
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}",
    )

    _configured = True
    logger.info("Logger 初始化完成，级别: {}", settings.log_level)
