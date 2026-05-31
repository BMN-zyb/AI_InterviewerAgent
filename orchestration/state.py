"""
全局状态定义（TypedDict），LangGraph 各节点共享
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict

from langchain_core.messages import BaseMessage


class InterviewState(TypedDict, total=False):
    """面试流程全局状态"""

    # ---- 会话 ID ----
    session_id: str
    user_id: str

    # ---- 用户输入 / 意图 ----
    user_input: str
    intent: str
    intent_confidence: float

    # ---- JD / 简历 ----
    jd_text: str
    jd_parsed: Dict[str, Any]
    resume_text: str
    resume_parsed: Dict[str, Any]

    # ---- RAG ----
    rag_context: str
    rag_sources: List[Dict[str, Any]]

    # ---- 题目与问答 ----
    question_plan: List[Dict[str, Any]]
    total_questions: int                  # ★ 补充：控制出题数量
    current_question_idx: int
    current_question: Dict[str, Any]
    current_question_text: str
    is_followup: bool
    qa_history: List[Dict[str, Any]]
    awaiting_answer: bool
    awaiting_evaluation: bool
    last_user_answer: str

    # ---- 追问控制 ----
    followup_count: int
    max_followup: int
    should_followup: bool
    followup_question: str

    # ---- 评分与报告 ----
    score_records: List[Dict[str, Any]]
    final_report: Dict[str, Any]
    study_plan: Dict[str, Any]
    github_recommendations: List[Dict[str, Any]]

    # ---- 难度 FSM ----
    current_difficulty: str
    consecutive_correct: int
    consecutive_wrong: int

    # ---- 记忆 ----
    short_term_context: List[str]
    long_term_weaknesses: List[str]
    weaknesses_to_remember: List[str]
    strengths: List[str]
    weaknesses: List[str]

    # ---- 技能 ----
    skill_name: str
    skill_state: Dict[str, Any]

    # ---- 输出 ----
    agent_reply: str
    interviewer_comment: str
    interview_finished: bool
    error: Optional[str]

    # ---- LangGraph 消息流 ----
    messages: List[BaseMessage]

    # ---- 强制结束标志 ----
    force_finish: bool