"""
JD 智能解析 Agent：
输入：岗位 JD 文本或招聘链接（链接由 MCP web_scraper 先抓成文本）
输出：结构化的 JD 解析结果（技术栈、职级、核心能力项）
"""
from __future__ import annotations

from typing import Any, Dict, List

from agents.base_agent import BaseAgent

# ★ 修复：不用 str.format()，改为占位符 __JD_TEXT__，避免 jd_text 含花括号时崩溃
SYSTEM_PROMPT = """\
你是资深技术面试官。请对下面的岗位 JD 进行深度解析，提取以下信息并以 JSON 输出：
1. title：岗位名称
2. level：职级（junior / mid / senior / staff / principal）
3. years_of_experience：最低经验要求（年，纯数字）
4. tech_stack：核心技术栈列表（按重要度降序）
5. nice_to_have：加分项技术栈
6. core_competencies：核心能力项（如系统设计、算法、沟通能力等）
7. industry：所属行业/领域
8. key_responsibilities：关键职责摘要（3-5 条）
9. summary：一句话岗位画像

严格 JSON 输出，不要有多余文字。

JD 内容：
__JD_TEXT__
"""


class JDAnalyzerAgent(BaseAgent):
    name = "jd_analyzer"
    description = "JD 智能解析：提取技术栈、职级、核心能力"

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        jd_text = state.get("jd_text", "").strip()
        if not jd_text:
            state["jd_parsed"] = {}
            state["error"] = "JD 文本为空"
            return state

        # ★ 用 replace 替换，彻底规避 jd_text 含 { } 导致的 KeyError
        prompt = SYSTEM_PROMPT.replace("__JD_TEXT__", jd_text)
        parsed = self.invoke_llm_json(prompt, "")

        # 规范化字段
        parsed.setdefault("tech_stack", [])
        parsed.setdefault("core_competencies", [])
        parsed.setdefault("level", "mid")
        parsed.setdefault("title", "未知岗位")

        state["jd_parsed"] = parsed
        state["tech_stack"] = [t.lower() for t in parsed.get("tech_stack", [])]
        return state


def jd_to_markdown(jd: Dict[str, Any]) -> str:
    """将 JD 解析结果转为可读的 Markdown（用于报告展示）"""
    lines: List[str] = []
    lines.append(f"### {jd.get('title', '未知岗位')} ({jd.get('level', '-')})")
    lines.append(f"- 行业：{jd.get('industry', '-')}")
    lines.append(f"- 经验要求：{jd.get('years_of_experience', '-')} 年")
    lines.append(f"- 技术栈：{', '.join(jd.get('tech_stack', []))}")
    if jd.get("nice_to_have"):
        lines.append(f"- 加分项：{', '.join(jd['nice_to_have'])}")
    lines.append(f"- 核心能力：{', '.join(jd.get('core_competencies', []))}")
    return "\n".join(lines)