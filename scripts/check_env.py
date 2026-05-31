"""环境检查脚本"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

import redis
import requests
from loguru import logger
from sqlalchemy import create_engine, text


def check_all() -> None:
    logger.info("🔍 开始环境检查...")
    checks = [
        ("Python 版本", check_python),
        ("必要依赖", check_deps),
        (".env 文件", check_env_file),
        ("MySQL 连接", check_mysql),
        ("Redis 连接", check_redis),
        ("Weaviate 连接", check_weaviate),
        ("DashScope API", check_dashscope),
    ]
    for name, fn in checks:
        try:
            fn()
            logger.success("✅ {}", name)
        except Exception as e:
            logger.error("❌ {} - {}", name, e)


def check_python():
    assert sys.version_info >= (3, 10), f"需要 Python 3.10+，当前 {sys.version}"


def check_deps():
    required = ["langchain", "langgraph", "llama_index", "fastapi", "redis", "sqlalchemy"]
    for dep in required:
        __import__(dep.replace("-", "_"))


def check_env_file():
    assert Path(".env").exists(), ".env 文件不存在，请复制 .env.example"


def check_mysql():
    from config import settings
    engine = create_engine(settings.mysql_url)
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))


def check_redis():
    from config import settings
    r = redis.Redis(
        host=settings.redis_host, port=settings.redis_port,
        password=settings.redis_password or None, decode_responses=True,
    )
    assert r.ping()


def check_weaviate():
    from config import settings
    resp = requests.get(f"{settings.weaviate_url}/v1/.well-known/ready", timeout=5)
    resp.raise_for_status()


def check_dashscope():
    from config import settings
    resp = requests.post(
        "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {settings.dashscope_api_key}",
            "Content-Type": "application/json",
        },
        json={"model": settings.llm_model, "messages": [{"role": "user", "content": "hi"}], "max_tokens": 5},
        timeout=10,
    )
    resp.raise_for_status()


if __name__ == "__main__":
    check_all()
