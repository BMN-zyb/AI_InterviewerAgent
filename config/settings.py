"""
全局配置：通过 pydantic-settings 读取 .env 环境变量
"""
from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用全局配置（自动从 .env 加载）"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---- LLM ----
    dashscope_api_key: str = Field(..., description="通义千问 API Key")
    llm_model: str = "qwen-max"
    embedding_model: str = "text-embedding-v3"
    llm_temperature: float = 0.7
    llm_max_tokens: int = 4096

    # ---- MySQL ----
    mysql_host: str = "127.0.0.1"
    mysql_port: int = 3306
    mysql_user: str = "interview_agent"
    mysql_password: str = ""
    mysql_database: str = "interview_agent"

    @property
    def mysql_url(self) -> str:
        return (
            f"mysql+pymysql://{self.mysql_user}:{self.mysql_password}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}"
            "?charset=utf8mb4"
        )

    # ---- Redis ----
    redis_host: str = "127.0.0.1"
    redis_port: int = 6379
    redis_password: Optional[str] = None
    redis_db: int = 0
    redis_short_term_ttl: int = 86400  # 短期记忆 24 小时过期

    # ---- Weaviate ----
    weaviate_url: str = "http://localhost:8080"
    weaviate_api_key: Optional[str] = None

    # ---- MCP / GitHub ----
    github_token: Optional[str] = None

    # ---- App ----
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    log_level: str = "INFO"
    public_url: str = "http://localhost:8000"

    # ---- RAG ----
    rag_top_k: int = 5
    rag_bm25_weight: float = 0.4
    rag_vector_weight: float = 0.6

    # ---- Difficulty FSM ----
    difficulty_levels: tuple = ("easy", "medium", "hard")
    consecutive_correct_to_upgrade: int = 2
    consecutive_wrong_to_downgrade: int = 2


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
