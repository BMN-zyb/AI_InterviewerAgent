"""
记忆管理器：统一封装短期 / 长期记忆的读写接口
新增：clear_weaknesses 方法
"""
from __future__ import annotations

from typing import Any, Dict, List

from loguru import logger


def _coerce_bool(val: Any) -> bool:
    """
    ★ 将 Redis 反序列化后可能的字符串布尔值转为真正的 bool
    "True" / "true" / 1 / True -> True
    "False" / "false" / 0 / False / None -> False
    """
    if isinstance(val, bool):
        return val
    if isinstance(val, int):
        return bool(val)
    if isinstance(val, str):
        return val.strip().lower() in ("true", "1", "yes")
    return bool(val)


def _sanitize_state(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    ★ 从 Redis 加载 state 后，修正关键布尔字段的类型
    防止 JSON 序列化/反序列化导致 True -> "True" 的问题
    """
    bool_fields = [
        "interview_finished", "awaiting_answer", "awaiting_evaluation",
        "should_followup", "force_finish", "is_followup",
    ]
    for field in bool_fields:
        if field in state:
            state[field] = _coerce_bool(state[field])

    int_fields = [
        "current_question_idx", "followup_count", "max_followup",
        "total_questions", "consecutive_correct", "consecutive_wrong",
    ]
    for field in int_fields:
        if field in state:
            try:
                state[field] = int(state[field])
            except (TypeError, ValueError):
                state[field] = 0

    return state


class MemoryManager:
    """记忆统一入口（惰性初始化，任何一个存储不可用时自动降级）"""

    def __init__(self) -> None:
        self._short_term = None
        self._long_term  = None

    @property
    def short_term(self):
        if self._short_term is None:
            from memory.short_term import ShortTermMemory
            self._short_term = ShortTermMemory()
        return self._short_term

    @property
    def long_term(self):
        if self._long_term is None:
            from memory.long_term import LongTermMemory
            self._long_term = LongTermMemory()
        return self._long_term

    # ── 短期记忆 ──────────────────────────────────────────────────────────────

    def save_session(self, session_id: str, state: Dict[str, Any]) -> None:
        try:
            self.short_term.save_state_snapshot(session_id, state)
        except Exception as e:
            logger.warning("save_session 失败（已忽略）：{}", e)

    def load_session(self, session_id: str) -> Dict[str, Any]:
        """★ 加载后自动修正布尔/整型字段类型"""
        try:
            raw = self.short_term.get_state_snapshot(session_id) or {}
            return _sanitize_state(raw)
        except Exception as e:
            logger.warning("load_session 失败（已忽略）：{}", e)
            return {}

    def add_turn(self, session_id: str, role: str, content: str) -> None:
        try:
            self.short_term.append_turn(session_id, role, content)
        except Exception as e:
            logger.warning("add_turn 失败（已忽略）：{}", e)

    # ── 长期记忆 ──────────────────────────────────────────────────────────────

    def get_weaknesses(self, user_id: str) -> List[str]:
        try:
            return self.long_term.get_weaknesses(user_id)
        except Exception as e:
            logger.warning("get_weaknesses 失败（已忽略）：{}", e)
            return []

    def append_weaknesses(self, user_id: str, weaknesses: List[str]) -> None:
        try:
            self.long_term.append_weaknesses(user_id, weaknesses)
        except Exception as e:
            logger.warning("append_weaknesses 失败（已忽略）：{}", e)

    def clear_weaknesses(self, user_id: str) -> bool:
        """
        ★ 新增：清除用户所有历史薄弱点
        Returns: True 成功, False 失败
        """
        try:
            lt = self.long_term
            if not lt._ensure_connected():
                logger.warning("MySQL 不可用，无法清除薄弱点")
                return False
            from sqlalchemy import select
            from memory.models import UserProfile
            with lt._SessionLocal() as session:
                profile = session.execute(
                    select(UserProfile).where(UserProfile.user_id == user_id)
                ).scalar_one_or_none()
                if profile:
                    profile.persistent_weaknesses = []
                    session.commit()
                    logger.info("已清除用户 {} 的长期记忆薄弱点", user_id)
                else:
                    logger.info("用户 {} 无历史记录，无需清除", user_id)
            return True
        except Exception as e:
            logger.warning("clear_weaknesses 失败：{}", e)
            return False

    def save_interview(
        self,
        user_id:    str,
        session_id: str,
        report:     Dict[str, Any],
        study_plan: Dict[str, Any],
    ) -> None:
        try:
            self.long_term.save_interview_record(
                user_id, session_id, report, study_plan, jd_title=""
            )
        except Exception as e:
            logger.warning("save_interview 失败（已忽略）：{}", e)


memory_manager = MemoryManager()