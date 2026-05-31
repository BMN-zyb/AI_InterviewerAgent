"""
Skill 基类：有状态的多轮交互能力模块
与无状态 Tool 不同，Skill 维护自己的会话状态。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict

from agents.base_agent import BaseAgent


class BaseSkill(BaseAgent, ABC):
    """Skill 基类"""

    name: str = "base_skill"
    description: str = ""
    trigger_keywords: list[str] = []

    def __init__(self) -> None:
        super().__init__()
        # skill_state 维护在 state["skill_state"] 中，由调用者注入

    def get_skill_state(self, state: Dict[str, Any]) -> Dict[str, Any]:
        return state.get("skill_state", {}) or {}

    def set_skill_state(self, state: Dict[str, Any], new_state: Dict[str, Any]) -> None:
        state["skill_state"] = new_state

    @abstractmethod
    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        ...
