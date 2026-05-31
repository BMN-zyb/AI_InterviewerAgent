"""
长期记忆（MySQL）：用户画像 + 历史薄弱点 + 面试记录
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from loguru import logger

from config import settings
from memory.models import Base, InterviewRecord, UserProfile


def _make_engine_and_session():
    """延迟导入，避免 MySQL 未启动时崩溃"""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    engine = create_engine(
        settings.mysql_url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
    )
    SessionLocal = sessionmaker(bind=engine)
    return engine, SessionLocal


class LongTermMemory:
    """基于 MySQL 的长期记忆（带容错）"""

    def __init__(self) -> None:
        self._engine      = None
        self._SessionLocal = None
        self._available   = None   # None=未检测, True/False=已检测

    def _ensure_connected(self) -> bool:
        """惰性连接，首次调用时尝试连接，失败则标记不可用"""
        if self._available is True:
            return True
        if self._available is False:
            return False
        # 首次检测
        try:
            self._engine, self._SessionLocal = _make_engine_and_session()
            # 测试连通性
            with self._engine.connect() as conn:
                conn.execute(__import__("sqlalchemy").text("SELECT 1"))
            self._available = True
            logger.info("MySQL 长期记忆已连接")
            return True
        except Exception as e:
            self._available = False
            logger.warning("MySQL 不可用，长期记忆降级为空：{}", e)
            return False

    def create_tables(self) -> None:
        if not self._ensure_connected():
            return
        try:
            Base.metadata.create_all(self._engine)
            logger.info("长期记忆表已创建")
        except Exception as e:
            logger.warning("创建表失败：{}", e)

    # ── 用户画像 ──────────────────────────────────────────────────────────────

    def get_or_create_profile(self, user_id: str) -> Optional[UserProfile]:
        if not self._ensure_connected():
            return None
        try:
            from sqlalchemy import select
            with self._SessionLocal() as session:
                profile = session.execute(
                    select(UserProfile).where(UserProfile.user_id == user_id)
                ).scalar_one_or_none()
                if profile is None:
                    profile = UserProfile(user_id=user_id)
                    session.add(profile)
                    session.commit()
                    session.refresh(profile)
                # ★ 关键：在 session 关闭前 eager 读取所有需要的字段
                weaknesses = list(profile.persistent_weaknesses or [])
                strengths  = list(profile.tech_strengths or [])
                total      = profile.total_interviews or 0
                # 构造一个普通对象返回，避免 detached instance 问题
                result = UserProfile.__new__(UserProfile)
                result.user_id                = user_id
                result.persistent_weaknesses  = weaknesses
                result.tech_strengths         = strengths
                result.total_interviews       = total
                return result
        except Exception as e:
            logger.warning("get_or_create_profile 失败：{}", e)
            return None

    def append_weaknesses(self, user_id: str, new_weaknesses: List[str]) -> None:
        if not self._ensure_connected():
            return
        try:
            from sqlalchemy import select
            with self._SessionLocal() as session:
                profile = session.execute(
                    select(UserProfile).where(UserProfile.user_id == user_id)
                ).scalar_one_or_none()
                if not profile:
                    profile = UserProfile(user_id=user_id)
                    session.add(profile)
                    session.flush()
                # ★ 在 session 内操作，不依赖懒加载
                existing: List[str] = list(profile.persistent_weaknesses or [])
                for w in new_weaknesses:
                    if w and w not in existing:
                        existing.append(w)
                profile.persistent_weaknesses = existing[:50]
                session.commit()
                logger.info("薄弱点已写入长期记忆：{} 条", len(existing))
        except Exception as e:
            logger.warning("append_weaknesses 失败：{}", e)

    def get_weaknesses(self, user_id: str) -> List[str]:
        if not self._ensure_connected():
            return []
        try:
            from sqlalchemy import select
            with self._SessionLocal() as session:
                profile = session.execute(
                    select(UserProfile).where(UserProfile.user_id == user_id)
                ).scalar_one_or_none()
                if not profile:
                    return []
                # ★ 在 session 内读取，避免 detached instance
                return list(profile.persistent_weaknesses or [])
        except Exception as e:
            logger.warning("get_weaknesses 失败：{}", e)
            return []

    # ── 面试记录 ──────────────────────────────────────────────────────────────

    def save_interview_record(
        self,
        user_id:    str,
        session_id: str,
        report:     Dict[str, Any],
        study_plan: Dict[str, Any],
        jd_title:   str = "",
    ) -> None:
        if not self._ensure_connected():
            return
        try:
            from sqlalchemy import select
            with self._SessionLocal() as session:
                record = InterviewRecord(
                    user_id        = user_id,
                    session_id     = session_id,
                    jd_title       = jd_title,
                    overall_score  = report.get("overall_score", 0),
                    recommendation = report.get("recommendation", ""),
                    report_json    = report,
                    study_plan_json= study_plan,
                    weaknesses     = report.get("weaknesses", []),
                )
                session.add(record)
                # 同时更新画像
                profile = session.execute(
                    select(UserProfile).where(UserProfile.user_id == user_id)
                ).scalar_one_or_none()
                if profile:
                    profile.total_interviews = (profile.total_interviews or 0) + 1
                session.commit()
                logger.info("面试记录已保存：session_id={}", session_id)
        except Exception as e:
            logger.warning("save_interview_record 失败：{}", e)