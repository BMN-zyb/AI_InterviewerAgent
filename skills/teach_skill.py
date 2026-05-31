"""
知识讲解技能：针对某个概念深入浅出讲解
★ 使用方式：/teach <概念>
"""
from __future__ import annotations

from typing import Any, Dict

from skills.base_skill import BaseSkill

PROMPT = """\
请用「面试官讲解」的口吻，对以下概念进行 3 层讲解：
1. 一句话定义
2. 核心原理（用生动类比解释）
3. 面试高频追问点（列出 3 个）

概念：__TOPIC__

要求：300 字以内，条理清晰，语言通俗易懂。
"""

USAGE_HINT = """\
📖 知识讲解使用方式：
  /teach RAG           → 讲解 RAG 概念
  /teach LoRA          → 讲解 LoRA 概念
  /teach 注意力机制     → 讲解 Attention 机制
"""


class TeachSkill(BaseSkill):
    name = "teach"
    description = "知识讲解：深入浅出讲解某个技术概念"
    trigger_keywords = ["讲解", "teach", "解释", "什么是"]

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        user_input = state.get("user_input", "").strip()

        # 移除 /teach 前缀
        if user_input.lower().startswith("/teach"):
            user_input = user_input[6:].strip()

        if not user_input:
            state["agent_reply"] = USAGE_HINT
            return state

        topic = user_input
        prompt = PROMPT.replace("__TOPIC__", topic)
        reply = self.invoke_llm(prompt, "", temperature=0.7)

        state["agent_reply"] = f"📖 **{topic}** 讲解：\n\n{reply}"
        self.logger.info(f"TeachSkill 讲解概念：{topic}")
        return state