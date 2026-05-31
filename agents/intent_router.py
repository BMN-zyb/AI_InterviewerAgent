"""
意图路由器 Agent：
根据用户输入，判断走哪条链路——面试/技能练习/闲聊/简历上传/JD 输入等
是整个编排层的入口。
"""
from __future__ import annotations

from typing import Any, Dict, Literal

from loguru import logger

from agents.base_agent import BaseAgent

IntentType = Literal[
    "start_interview",   # 开始一次完整面试
    "answer_question",   # 回答当前面试题目
    "upload_resume",     # 上传简历
    "input_jd",          # 输入 JD
    "use_skill",         # 使用技能（quiz/teach/compare/project）
    "chat",              # 普通闲聊
    "unknown",
]

# ★ 修复1：JSON 示例中的花括号双写转义 {{ }}
SYSTEM_PROMPT = """你是一个意图识别专家。根据用户输入，判断其意图类别。
候选类别：
- start_interview：用户想要开始一场模拟面试
- answer_question：用户正在回答上一道面试题
- upload_resume：用户表达了想上传/提交简历的意图
- input_jd：用户粘贴了岗位 JD 或描述
- use_skill：用户想使用某项技能（快速测验/知识讲解/项目亮点提炼/技术对比）
- chat：普通聊天、问候、咨询

输出格式（严格 JSON）：
{{"intent": "<类别>", "confidence": 0.0~1.0, "skill": "quiz|teach|project|compare|null"}}
"""


class IntentRouterAgent(BaseAgent):
    name = "intent_router"
    description = "意图路由器：分流用户请求"

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        user_input = state.get("user_input", "").strip()
        if not user_input:
            state["intent"] = "chat"
            return state

        # 快捷指令（不走 LLM，节省 token）
        if user_input.startswith("/interview"):
            state["intent"] = "start_interview"
            return state

        if user_input.startswith("/skill"):
            state["intent"] = "use_skill"
            return state

        if user_input.startswith("/jd"):
            state["intent"] = "input_jd"
            state["jd_text"] = user_input[3:].strip()
            return state

        # ★ 修复2：避免 user_input 中含 { } 导致 format 报错
        user_prompt = f"用户输入：{user_input}"

        parsed = self.invoke_llm_json(SYSTEM_PROMPT, user_prompt)

        intent = parsed.get("intent", "chat")

        logger.info(
            "意图识别: {} -> {} (conf={})",
            user_input[:50],
            intent,
            parsed.get("confidence"),
        )

        state["intent"] = intent
        state["intent_confidence"] = parsed.get("confidence", 0.0)

        if parsed.get("skill"):
            state["skill_name"] = parsed["skill"]

        return state