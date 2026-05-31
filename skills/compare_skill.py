"""
技术对比技能：两个技术方案的对比分析
★ 使用方式：/compare <技术A> vs <技术B>
"""
from __future__ import annotations

from typing import Any, Dict

from skills.base_skill import BaseSkill

PROMPT = """\
请对以下两个技术方案进行专业对比分析：

对比对象：__SUBJECTS__

请从以下 5 个维度分析，并给出综合建议：
1. 性能表现
2. 实现复杂度
3. 可维护性
4. 适用场景
5. 面试常考点

输出 JSON：
{{
  "subject_a": "技术A名称",
  "subject_b": "技术B名称",
  "comparison": [
    {{"dimension": "维度名", "a": "A的表现", "b": "B的表现", "winner": "a或b或tie"}}
  ],
  "summary": "综合建议（100字以内）",
  "interview_tips": "面试中如何回答对比题的技巧"
}}
"""

USAGE_HINT = """\
🔀 技术对比使用方式：
  /compare RAG vs Fine-tuning
  /compare Redis vs Memcached
  /compare BM25 vs 向量检索
"""


class CompareSkill(BaseSkill):
    name = "compare"
    description = "技术对比：多维度对比两个技术方案"
    trigger_keywords = ["对比", "compare", "区别", "差异"]

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        user_input = state.get("user_input", "").strip()

        # 移除 /compare 前缀
        if user_input.lower().startswith("/compare"):
            user_input = user_input[8:].strip()

        if not user_input:
            state["agent_reply"] = USAGE_HINT
            return state

        subjects = user_input
        prompt = PROMPT.replace("__SUBJECTS__", subjects)
        parsed = self.invoke_llm_json(prompt, "")

        subject_a = parsed.get("subject_a", "A")
        subject_b = parsed.get("subject_b", "B")
        rows = parsed.get("comparison", [])
        summary = parsed.get("summary", "")
        tips = parsed.get("interview_tips", "")

        # 构建对比表格文本
        lines = [f"🔀 **{subject_a}** vs **{subject_b}** 对比分析\n"]
        lines.append(f"{'维度':<12} {''+subject_a:<20} {''+subject_b:<20} {'胜者':<6}")
        lines.append("─" * 60)
        winner_map = {"a": subject_a, "b": subject_b, "tie": "平局"}
        for r in rows:
            winner = winner_map.get(r.get("winner", "tie"), "平局")
            lines.append(
                f"{r.get('dimension',''):<12} "
                f"{r.get('a',''):<20} "
                f"{r.get('b',''):<20} "
                f"{winner:<6}"
            )

        if summary:
            lines.append(f"\n💡 综合建议：{summary}")
        if tips:
            lines.append(f"\n🎯 面试技巧：{tips}")

        state["agent_reply"] = "\n".join(lines)
        self.logger.info(f"CompareSkill 对比：{subjects}")
        return state