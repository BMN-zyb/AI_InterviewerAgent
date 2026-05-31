"""
技能注册器：可插拔扩展
"""
from __future__ import annotations

from typing import Dict, Optional

from skills.base_skill import BaseSkill
from skills.compare_skill import CompareSkill
from skills.project_skill import ProjectSkill
from skills.quiz_skill import QuizSkill
from skills.teach_skill import TeachSkill


class SkillRegistry:
    """技能注册表"""

    def __init__(self) -> None:
        self._skills: Dict[str, BaseSkill] = {}

    def register(self, skill: BaseSkill) -> None:
        self._skills[skill.name] = skill

    def get(self, name: str) -> Optional[BaseSkill]:
        return self._skills.get(name)

    def list_skills(self) -> list[str]:
        return list(self._skills.keys())


skill_registry = SkillRegistry()
# 注册内置技能
for _cls in (QuizSkill, TeachSkill, ProjectSkill, CompareSkill):
    skill_registry.register(_cls())  # type: ignore[operator]
