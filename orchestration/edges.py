"""
条件边 / 路由逻辑：根据 state 动态选择下一个节点
"""
from __future__ import annotations

from orchestration.state import InterviewState


def route_by_intent(state: InterviewState) -> str:
    """按意图分流"""
    intent = state.get("intent", "chat")
    mapping = {
        "start_interview": "load_memory",
        "input_jd": "jd_analyze",
        "upload_resume": "resume_analyze",
        "answer_question": "evaluate_one",
        "use_skill": "skill_dispatch",
        "chat": "chat",
    }
    return mapping.get(intent, "chat")


def route_after_jd(state: InterviewState) -> str:
    """JD 分析完成后：有简历则分析简历，否则直接 RAG"""
    if state.get("error"):
        return "rag_retrieve"
    resume_text = state.get("resume_text", "").strip()
    if resume_text:
        return "resume_analyze"
    return "rag_retrieve"


def route_after_resume(state: InterviewState) -> str:
    """简历分析完成后：进入 RAG 检索"""
    if state.get("error"):
        return "chat"
    return "rag_retrieve"


def route_after_plan(state: InterviewState) -> str:
    """出题规划完成后：进入第一题提问"""
    if state.get("error") or not state.get("question_plan"):
        return "chat"
    return "ask"


def route_after_evaluate(state: InterviewState) -> str:
    """
    单题评估后路由：
    - 需要追问 -> ask（追问）
    - 面试结束 -> generate_report
    - 否则 -> ask（下一题）
    """
    if state.get("interview_finished", False):
        return "generate_report"
    # should_followup 或正常下一题，都走 ask
    return "ask"


def route_after_report(state: InterviewState) -> str:
    """面试报告生成后：进入复习计划"""
    return "study_plan"