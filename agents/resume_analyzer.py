"""
简历深度匹配 Agent：
- 输入：简历文本 + JD 解析结果
- 输出：匹配度评分、优势、短板、匹配明细
"""
from __future__ import annotations

from typing import Any, Dict

from agents.base_agent import BaseAgent

# ★ 修复1：JSON 示例中所有花括号双写转义 {{ }}
SYSTEM_PROMPT = """\
你是资深技术面试官。基于以下「岗位 JD」与「候选人简历」，输出结构化的匹配分析。

岗位 JD：
{jd_summary}

候选人简历：
{resume_text}

输出 JSON 结构（严格按此格式，不要输出其他内容）：
{{
  "overall_score": 0到100的整数,
  "match_level": "low或medium或high",
  "strengths": ["优势1", "优势2", "优势3"],
  "weaknesses": ["短板1", "短板2", "短板3"],
  "tech_match": {{
    "技术名": {{"matched": true, "evidence": "简历中的证据"}}
  }},
  "experience_fit": "under或fit或over",
  "highlights": ["值得深挖的点1", "值得深挖的点2"],
  "red_flags": ["潜在风险1"],
  "summary": "一句话总结"
}}
"""


class ResumeAnalyzerAgent(BaseAgent):
    name = "resume_analyzer"
    description = "简历深度匹配：与 JD 对比打分"

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        resume_text = state.get("resume_text", "").strip()
        jd_parsed = state.get("jd_parsed", {})

        if not resume_text:
            state["resume_parsed"] = {}
            state["error"] = "简历内容为空"
            return state
        if not jd_parsed:
            state["error"] = "请先解析 JD"
            return state

        jd_summary = (
            f"岗位：{jd_parsed.get('title', '未知')}\n"
            f"技术栈：{', '.join(jd_parsed.get('tech_stack', []))}\n"
            f"核心能力：{', '.join(jd_parsed.get('core_competencies', []))}\n"
            f"经验要求：{jd_parsed.get('years_of_experience', '未知')} 年"
        )

        # ★ 修复2：jd_summary / resume_text 本身可能含 { }，改用模板替换而非 format
        prompt = SYSTEM_PROMPT.replace("{jd_summary}", jd_summary).replace(
            "{resume_text}", resume_text
        )

        parsed = self.invoke_llm_json(prompt, "")

        state["resume_parsed"] = parsed
        # ★ 修复3：统一使用 weaknesses_to_remember（与 state.py / node_save_memory 对齐）
        state["weaknesses_to_remember"] = parsed.get("weaknesses", [])
        state["strengths"] = parsed.get("strengths", [])
        return state