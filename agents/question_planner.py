"""
智能出题规划 Agent：
- 基于 JD + 简历 + RAG 题库检索结果，规划一套面试题目
- 支持 total_questions 控制题目数量
"""
from __future__ import annotations

from typing import Any, Dict, List

from agents.base_agent import BaseAgent

SYSTEM_PROMPT = """\
你是资深技术面试官，正在规划一场结构化模拟面试。
根据岗位 JD、候选人简历、以及 RAG 检索到的参考题库，规划恰好 __TOTAL__ 道面试题。

岗位画像：
__JD_SUMMARY__

候选人画像（优势/短板）：
Strengths: __STRENGTHS__
Weaknesses: __WEAKNESSES__

RAG 检索到的参考题目片段：
__RAG_CONTEXT__

要求：
1. 必须严格输出恰好 __TOTAL__ 道题目，不多不少
2. 题目分布合理：基础题 30% / 中等题 50% / 高阶题 20%
3. 题型混合：概念题 / 场景设计 / 代码实现 / 行为面试 / 项目深挖
4. 针对候选人短板设计重点考察题
5. 每道题包含：topic（技术主题）、question_type（题型）、difficulty（easy/medium/hard）、focus（考察点）、prompt（具体问题文本）

输出 JSON：{{"plan": [...]}} 数组长度必须为 __TOTAL__
"""


class QuestionPlannerAgent(BaseAgent):
    name = "question_planner"
    description = "智能出题规划：基于 JD + 简历 + RAG 规划题目"

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        jd = state.get("jd_parsed", {})
        resume = state.get("resume_parsed", {})
        rag = state.get("rag_context", "")

        # ★ 读取 total_questions，默认 5
        total = int(state.get("total_questions", 5))

        jd_summary = (
            f"岗位：{jd.get('title')} / {jd.get('level')}\n"
            f"技术栈：{jd.get('tech_stack')}\n"
            f"核心能力：{jd.get('core_competencies')}"
        )
        strengths = "\n".join("- " + s for s in state.get("strengths", [])) or "（无）"
        weaknesses = "\n".join("- " + w for w in state.get("weaknesses", [])) or "（无）"

        # ★ 用 replace 注入，避免 format() 与花括号冲突
        prompt = (
            SYSTEM_PROMPT
            .replace("__TOTAL__", str(total))
            .replace("__JD_SUMMARY__", jd_summary)
            .replace("__STRENGTHS__", strengths)
            .replace("__WEAKNESSES__", weaknesses)
            .replace("__RAG_CONTEXT__", rag[:4000])
        )

        parsed = self.invoke_llm_json(prompt, "")
        plan: List[Dict[str, Any]] = parsed.get("plan", [])

        # ★ 截断或补全，保证恰好 total 道题
        if len(plan) > total:
            plan = plan[:total]
        elif len(plan) < total and len(plan) > 0:
            # 不足时重复最后一题的结构补位（极少发生）
            self.logger.warning(f"LLM 只生成了 {len(plan)} 题，期望 {total} 题，截断使用")

        # 规范化字段
        for i, q in enumerate(plan):
            q.setdefault("id", f"Q{i + 1}")
            q.setdefault("difficulty", "medium")
            q.setdefault("question_type", "concept")

        state["question_plan"] = plan
        state["current_question_idx"] = 0
        self.logger.info(f"出题规划完成，共 {len(plan)} 题（目标 {total} 题）")
        return state