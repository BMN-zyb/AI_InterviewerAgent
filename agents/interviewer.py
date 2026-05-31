"""
AI 面试官 Agent：多轮交互核心
- 支持追问深挖（followup）
- 支持面试官主动判断结束
- 评估后给出点评再出下一题
"""
from __future__ import annotations

from typing import Any, Dict, List

from agents.base_agent import BaseAgent

# ── 正常出题 Prompt ──────────────────────────────────────────────────────────
ASK_PROMPT_TEMPLATE = """\
你是资深技术面试官，正在进行一场真实的模拟面试对话。

岗位：__TITLE__（__LEVEL__）
当前题目（ID: __QID__，第 __CUR__ / __TOTAL__ 题）：
- 主题：__TOPIC__
- 题型：__QUESTION_TYPE__
- 难度：__DIFFICULTY__
- 考察点：__FOCUS__
- 预设问题：__PROMPT__

候选人简历摘要：__RESUME_SUMMARY__
当前面试难度状态：__DIFFICULTY_STATE__
近期问答记录：
__HISTORY__

【任务】请你以面试官身份，自然地向候选人提出这道题。
要求：
1. 语言口语化、专业，像真实面试场景的对话
2. 可以在正式提问前，用一句话简短衔接（如"好的，接下来我们聊一个系统设计的问题"）
3. 不要加「面试官：」前缀
4. 问题控制在 120 字以内

输出 JSON：{"question": "完整提问内容", "is_followup": false}
"""

# ── 追问 Prompt ───────────────────────────────────────────────────────────────
FOLLOWUP_PROMPT_TEMPLATE = """\
你是资深技术面试官，正在对候选人的回答进行深挖追问。

刚才的问题：__ORIGINAL_Q__
候选人的回答：__CANDIDATE_ANSWER__
评估发现的不足：__KEY_MISSING__

【任务】请根据候选人回答中的不足或值得深挖的点，提出一个追问。
要求：
1. 追问要有针对性，直接切入候选人回答的薄弱环节
2. 语气自然，像真实面试官追问
3. 不要加「面试官：」前缀
4. 控制在 80 字以内

输出 JSON：{"question": "追问内容", "is_followup": true}
"""

# ── 点评 Prompt ───────────────────────────────────────────────────────────────
COMMENT_PROMPT_TEMPLATE = """\
你是资深技术面试官，刚才评估了候选人对一道题的回答。

题目：__QUESTION__
候选人回答：__ANSWER__
评分结果：__SCORE__
遗漏的关键点：__MISSING__

【任务】给候选人一句简短的点评（肯定亮点或指出不足），然后自然过渡到下一题。
要求：
1. 点评控制在 60 字以内，口语化
2. 不要直接说"你的回答得了X分"
3. 不要加「面试官：」前缀
4. 只输出点评语，不要输出下一道题

输出 JSON：{"comment": "点评内容"}
"""

# ── 结束语 Prompt ─────────────────────────────────────────────────────────────
FINISH_PROMPT_TEMPLATE = """\
你是资深技术面试官，本场面试已经结束。

岗位：__TITLE__
面试共 __TOTAL__ 题，整体表现印象：__IMPRESSION__

【任务】请给出一段自然的结束语，感谢候选人参与，并简短说明接下来的安排。
要求：
1. 控制在 80 字以内，口语化温和
2. 不要加「面试官：」前缀

输出 JSON：{"farewell": "结束语内容"}
"""


class InterviewerAgent(BaseAgent):
    name = "interviewer"
    description = "AI 面试官：多轮追问深挖"

    # ── 内部工具方法 ─────────────────────────────────────────────────────────

    def _build_history_text(self, qa_history: List[Dict[str, Any]], last_n: int = 3) -> str:
        if not qa_history:
            return "（无）"
        recent = qa_history[-last_n:]
        lines = []
        for i, h in enumerate(recent):
            lines.append(f"[问] {h.get('question', '')}")
            lines.append(f"[答] {h.get('answer', '')}")
        return "\n".join(lines)

    def ask_question(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """出下一道计划题目"""
        plan: List[Dict[str, Any]] = state.get("question_plan", [])
        idx: int = state.get("current_question_idx", 0)
        jd = state.get("jd_parsed", {})
        resume = state.get("resume_parsed", {})
        history_text = self._build_history_text(state.get("qa_history", []))

        current_q = plan[idx]
        prompt = (
            ASK_PROMPT_TEMPLATE
            .replace("__TITLE__", str(jd.get("title", "技术岗")))
            .replace("__LEVEL__", str(jd.get("level", "mid")))
            .replace("__QID__", str(current_q.get("id", idx + 1)))
            .replace("__CUR__", str(idx + 1))
            .replace("__TOTAL__", str(len(plan)))
            .replace("__TOPIC__", str(current_q.get("topic", "")))
            .replace("__QUESTION_TYPE__", str(current_q.get("question_type", "")))
            .replace("__DIFFICULTY__", str(current_q.get("difficulty", "")))
            .replace("__FOCUS__", str(current_q.get("focus", "")))
            .replace("__PROMPT__", str(current_q.get("prompt", "")))
            .replace("__RESUME_SUMMARY__", str(resume.get("summary", ""))[:300])
            .replace("__DIFFICULTY_STATE__", str(state.get("current_difficulty", "medium")))
            .replace("__HISTORY__", history_text)
        )

        parsed = self.invoke_llm_json(prompt, "")
        state["current_question"] = current_q
        state["current_question_text"] = parsed.get("question", current_q.get("prompt", ""))
        state["is_followup"] = False
        state["agent_reply"] = state["current_question_text"]
        state["awaiting_answer"] = True
        state["followup_count"] = 0          # 重置追问计数
        state["should_followup"] = False
        return state

    def ask_followup(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """基于上一轮回答进行追问"""
        last_qa = (state.get("qa_history") or [{}])[-1]
        score = last_qa.get("score", {})
        missing = score.get("key_missing", [])

        prompt = (
            FOLLOWUP_PROMPT_TEMPLATE
            .replace("__ORIGINAL_Q__", str(state.get("current_question_text", "")))
            .replace("__CANDIDATE_ANSWER__", str(state.get("last_user_answer", ""))[:500])
            .replace("__KEY_MISSING__", str(missing)[:300])
        )

        parsed = self.invoke_llm_json(prompt, "")
        followup_q = parsed.get("question", "")

        state["current_question_text"] = followup_q
        state["is_followup"] = True
        state["agent_reply"] = followup_q
        state["awaiting_answer"] = True
        state["followup_count"] = state.get("followup_count", 0) + 1
        state["should_followup"] = False
        return state

    def make_comment(self, state: Dict[str, Any]) -> str:
        """对刚才的回答给出简短点评"""
        last_qa = (state.get("qa_history") or [{}])[-1]
        score = last_qa.get("score", {})
        missing = score.get("key_missing", [])

        prompt = (
            COMMENT_PROMPT_TEMPLATE
            .replace("__QUESTION__", str(state.get("current_question_text", "")))
            .replace("__ANSWER__", str(state.get("last_user_answer", ""))[:400])
            .replace("__SCORE__", str(score))
            .replace("__MISSING__", str(missing)[:200])
        )
        parsed = self.invoke_llm_json(prompt, "")
        return parsed.get("comment", "")

    def make_farewell(self, state: Dict[str, Any]) -> str:
        """生成结束语"""
        jd = state.get("jd_parsed", {})
        plan = state.get("question_plan", [])
        # 根据平均分给出印象
        records = state.get("score_records", [])
        if records:
            scores = []
            for r in records:
                s = r.get("score", {})
                if isinstance(s, dict):
                    vals = [v for v in s.values() if isinstance(v, (int, float))]
                    if vals:
                        scores.append(sum(vals) / len(vals))
            avg = sum(scores) / len(scores) if scores else 5
            impression = "整体表现不错" if avg >= 7 else "有一些提升空间"
        else:
            impression = "感谢参与"

        prompt = (
            FINISH_PROMPT_TEMPLATE
            .replace("__TITLE__", str(jd.get("title", "技术岗")))
            .replace("__TOTAL__", str(len(plan)))
            .replace("__IMPRESSION__", impression)
        )
        parsed = self.invoke_llm_json(prompt, "")
        return parsed.get("farewell", "感谢你参与本次模拟面试，祝你面试顺利！")

    # ── 主入口 ────────────────────────────────────────────────────────────────

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        plan: List[Dict[str, Any]] = state.get("question_plan", [])
        idx: int = state.get("current_question_idx", 0)

        if idx >= len(plan):
            state["interview_finished"] = True
            state["agent_reply"] = self.make_farewell(state)
            return state

        # 判断是否需要追问
        should_followup = state.get("should_followup", False)
        followup_count = state.get("followup_count", 0)
        max_followup = state.get("max_followup", 2)

        if should_followup and followup_count < max_followup:
            return self.ask_followup(state)
        else:
            return self.ask_question(state)