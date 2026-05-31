"""
闲聊 Agent：处理非面试主链路的日常聊天
"""
from __future__ import annotations

from typing import Any, Dict

from agents.base_agent import BaseAgent

SYSTEM_PROMPT = (
    "你是 InterviewAgent 的助手，一位友好、专业的 AI 伙伴。"
    "用户不是在正式面试，而是闲聊/提问/咨询。请简短回复（100 字以内）。"
)


class ChatAgent(BaseAgent):
    name = "chat"
    description = "闲聊 Agent"

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        user_input = state.get("user_input", "")
        # ★ 修复：invoke_llm 不接受 temperature 参数，temperature 在构造时设置
        reply = self.invoke_llm(SYSTEM_PROMPT, user_input)
        state["agent_reply"] = reply
        return state