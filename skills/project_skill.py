"""
项目亮点提炼技能：帮候选人从简历项目中提炼 STAR 表达
★ 使用方式：/project <项目描述>
"""
from __future__ import annotations

from typing import Any, Dict

from skills.base_skill import BaseSkill

PROMPT = """\
基于候选人的项目描述，提炼 3 条 STAR（情境/任务/行动/结果）表达，便于面试中展示亮点。

项目描述：
__PROJECT_DESC__

要求：
1. 每条 STAR 要突出技术难点和个人贡献
2. 结果部分尽量量化（如"性能提升40%"）
3. 提炼面试中最容易被追问的关键词

输出 JSON：
{{
  "highlights": [
    {{
      "title": "亮点标题",
      "star": "S(情境): ... T(任务): ... A(行动): ... R(结果): ...",
      "keyword": "核心关键词",
      "likely_followup": "面试官可能的追问"
    }}
  ],
  "elevator_pitch": "30秒电梯演讲版本（用于自我介绍）"
}}
"""

USAGE_HINT = """\
💼 项目亮点提炼使用方式：
  /project 我负责开发了一个RAG知识库系统，使用Weaviate向量数据库...
  （粘贴你的项目描述，AI帮你提炼STAR亮点）
"""


class ProjectSkill(BaseSkill):
    name = "project"
    description = "项目亮点提炼：从项目描述中提炼 STAR 表达"
    trigger_keywords = ["项目", "project", "亮点"]

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        user_input = state.get("user_input", "").strip()

        # 移除 /project 前缀
        if user_input.lower().startswith("/project"):
            user_input = user_input[8:].strip()

        if not user_input:
            state["agent_reply"] = USAGE_HINT
            return state

        prompt = PROMPT.replace("__PROJECT_DESC__", user_input[:2000])
        parsed = self.invoke_llm_json(prompt, "")

        highlights = parsed.get("highlights", [])
        elevator   = parsed.get("elevator_pitch", "")

        lines = [f"💼 为你提炼了 {len(highlights)} 个项目亮点：\n"]
        for i, h in enumerate(highlights, 1):
            lines.append(f"【亮点 {i}】{h.get('title', '')}")
            lines.append(f"  {h.get('star', '')}")
            lines.append(f"  🏷️  关键词：{h.get('keyword', '')}")
            lines.append(f"  ❓ 可能追问：{h.get('likely_followup', '')}")
            lines.append("")

        if elevator:
            lines.append(f"🎤 30秒电梯演讲：\n{elevator}")

        state["agent_reply"] = "\n".join(lines)
        self.logger.info(f"ProjectSkill 提炼亮点：{user_input[:30]}...")
        return state