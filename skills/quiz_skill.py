"""
快速测验技能：出题 -> 收答 -> 即时评分
使用方式：
  /quiz <主题>     → 出题（如 /quiz RAG）
  /quiz <你的答案> → 提交答案评分（在已出题之后）
"""
from __future__ import annotations

from typing import Any, Dict, List

from skills.base_skill import BaseSkill

ASK_PROMPT = """\
请出一道关于「__TOPIC__」的面试测验题，难度 __DIFFICULTY__。
要求：题目清晰、有明确答案、适合口头作答（不要出选择题）。
输出 JSON：
{{
  "question": "题目内容",
  "answer": "标准答案要点（字符串，2-3条要点用分号分隔）",
  "difficulty": "easy或medium或hard"
}}
"""

GRADE_PROMPT = """\
请评判候选人的回答质量。

题目：__QUESTION__
标准答案要点：__REFERENCE__
候选人回答：__ANSWER__

评分标准（0~10）：
- 10分：完全正确且有延伸
- 7~9分：基本正确，有小缺漏
- 4~6分：部分正确
- 0~3分：明显错误或不知道

输出 JSON：
{{
  "score": 分数整数,
  "feedback": "一句话点评",
  "correct_points": ["答对的点1", "答对的点2"],
  "missing_points": ["遗漏的点1", "遗漏的点2"]
}}
"""

USAGE_HINT = """\
📝 快速测验使用方式：
  /quiz              → 出一道 Python 基础题
  /quiz RAG          → 出一道关于 RAG 的题目
  （出题后）再次输入 /quiz <你的答案> 提交回答
"""


def _to_str(val: Any) -> str:
    """将任意类型安全转为字符串（处理 LLM 可能返回 list 的情况）"""
    if isinstance(val, list):
        return "；".join(str(v) for v in val)
    if val is None:
        return ""
    return str(val)


class QuizSkill(BaseSkill):
    name = "quiz"
    description = "快速测验：出题+即时评分（两步交互）"
    trigger_keywords = ["测验", "quiz", "考我", "出题"]

    def _is_new_quiz_request(self, user_input: str, skill_state: Dict[str, Any]) -> bool:
        """
        判断是否为新出题请求：
        - phase == "ask"（没有待答题目）→ 一定是出题请求
        - user_input 非常短（<=8字）→ 视为主题关键词，出新题
        """
        phase = skill_state.get("phase", "ask")
        if phase == "ask":
            return True
        # phase == "answer" 时，输入很短才视为新出题请求
        return len(user_input.strip()) <= 8

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        skill_state = self.get_skill_state(state)
        user_input  = state.get("user_input", "").strip()

        # 移除 /quiz 前缀
        if user_input.lower().startswith("/quiz"):
            user_input = user_input[5:].strip()

        phase = skill_state.get("phase", "ask")

        # ── 出题阶段 ──────────────────────────────────────────────────────────
        if self._is_new_quiz_request(user_input, skill_state):
            topic      = user_input if user_input else "Python 基础"
            difficulty = _to_str(state.get("current_difficulty", "medium"))

            prompt = (
                ASK_PROMPT
                .replace("__TOPIC__", topic)
                .replace("__DIFFICULTY__", difficulty)
            )
            parsed   = self.invoke_llm_json(prompt, "")
            question = _to_str(parsed.get("question", ""))
            # ★ 关键：answer 字段强制转 str，防止 LLM 返回 list
            reference = _to_str(parsed.get("answer", ""))

            new_skill_state = {
                "phase":     "answer",
                "question":  question,
                "reference": reference,   # 始终是 str
                "topic":     topic,
            }
            self.set_skill_state(state, new_skill_state)

            state["agent_reply"] = (
                f"📝 测验题目（主题：{topic}）：\n\n"
                f"{question}\n\n"
                f"💡 出题后请输入 /quiz <你的答案> 提交评分"
            )
            self.logger.info(f"QuizSkill 出题：topic={topic}, question={question[:50]}")

        # ── 评分阶段 ──────────────────────────────────────────────────────────
        else:
            question  = _to_str(skill_state.get("question",  ""))
            reference = _to_str(skill_state.get("reference", ""))
            topic     = _to_str(skill_state.get("topic",     ""))
            answer    = user_input

            if not question:
                state["agent_reply"] = USAGE_HINT
                self.set_skill_state(state, {"phase": "ask"})
                return state

            prompt = (
                GRADE_PROMPT
                .replace("__QUESTION__",  question)
                .replace("__REFERENCE__", reference)
                .replace("__ANSWER__",    answer)
            )
            parsed       = self.invoke_llm_json(prompt, "")
            score        = parsed.get("score", 0)
            feedback     = _to_str(parsed.get("feedback", ""))
            correct_pts  = parsed.get("correct_points", [])
            missing_pts  = parsed.get("missing_points", [])

            # 保证是列表
            if isinstance(correct_pts, str): correct_pts = [correct_pts]
            if isinstance(missing_pts, str): missing_pts = [missing_pts]

            lines = [f"✅ 得分：{score}/10    {feedback}"]
            if correct_pts:
                lines.append("\n答对的点：")
                lines += [f"  ✓ {p}" for p in correct_pts]
            if missing_pts:
                lines.append("\n遗漏的点：")
                lines += [f"  ✗ {p}" for p in missing_pts]
            lines.append("\n💡 输入 /quiz <主题> 继续下一题")

            state["agent_reply"] = "\n".join(lines)
            # 重置为出题阶段
            self.set_skill_state(state, {"phase": "ask"})
            self.logger.info(f"QuizSkill 评分：topic={topic}, score={score}")

        return state