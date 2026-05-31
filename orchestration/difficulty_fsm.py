"""
动态难度状态机：
连续答对 -> 自动升难度；连续答错 -> 自动降难度
三级：easy / medium / hard
"""
from __future__ import annotations

from typing import Any, Dict

from loguru import logger

from config import settings

LEVELS = settings.difficulty_levels
ORDER = {lv: i for i, lv in enumerate(LEVELS)}


def update_difficulty(state: Dict[str, Any]) -> None:
    """
    在每次单题评估后调用，根据 is_correct 更新难度。
    规则：
      - 连续答对 >= N 次 -> 升一档
      - 连续答错 >= N 次 -> 降一档
      - 否则保持
    """
    is_correct = state.get("last_correctness", False)
    current = state.get("current_difficulty", "medium")
    cons_correct = state.get("consecutive_correct", 0)
    cons_wrong = state.get("consecutive_wrong", 0)

    if is_correct:
        cons_correct += 1
        cons_wrong = 0
    else:
        cons_wrong += 1
        cons_correct = 0

    new_level = current
    idx = ORDER.get(current, 1)

    if cons_correct >= settings.consecutive_correct_to_upgrade and idx < len(LEVELS) - 1:
        new_level = LEVELS[idx + 1]
        cons_correct = 0
        logger.info("📈 难度上升：{} -> {}", current, new_level)
    elif cons_wrong >= settings.consecutive_wrong_to_downgrade and idx > 0:
        new_level = LEVELS[idx - 1]
        cons_wrong = 0
        logger.info("📉 难度下降：{} -> {}", current, new_level)

    state["current_difficulty"] = new_level
    state["consecutive_correct"] = cons_correct
    state["consecutive_wrong"] = cons_wrong
