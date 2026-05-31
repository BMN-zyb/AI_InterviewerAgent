"""
DAG 节点函数实现：每个节点对应一个 Agent.run() 调用
"""
from __future__ import annotations

from typing import Any, Dict

from loguru import logger

from agents import (
    ChatAgent,
    EvaluatorAgent,
    IntentRouterAgent,
    InterviewerAgent,
    JDAnalyzerAgent,
    QuestionPlannerAgent,
    ResumeAnalyzerAgent,
    StudyPlannerAgent,
)
from orchestration.state import InterviewState

# 单例（避免重复初始化 LLM）
_intent_router = IntentRouterAgent()
_jd_analyzer = JDAnalyzerAgent()
_resume_analyzer = ResumeAnalyzerAgent()
_question_planner = QuestionPlannerAgent()
_interviewer = InterviewerAgent()
_evaluator = EvaluatorAgent()
_study_planner = StudyPlannerAgent()
_chat = ChatAgent()


def node_route(state: InterviewState) -> InterviewState:
    """
    意图路由节点。
    如果调用方已经设置了 intent（CLI/API 直接注入），则跳过 LLM 识别。
    """
    logger.debug(">> node_route")
    if state.get("intent") in (
        "start_interview", "answer_question",
        "input_jd", "upload_resume", "use_skill",
    ):
        logger.debug(f"  intent 已预设为 {state['intent']}，跳过 LLM 路由")
        return dict(state)  # type: ignore[return-value]
    return _intent_router.run(dict(state))  # type: ignore[arg-type, return-value]


def node_jd_analyze(state: InterviewState) -> InterviewState:
    logger.debug(">> node_jd_analyze")
    return _jd_analyzer.run(dict(state))  # type: ignore[arg-type, return-value]


def node_resume_analyze(state: InterviewState) -> InterviewState:
    logger.debug(">> node_resume_analyze")
    return _resume_analyzer.run(dict(state))  # type: ignore[arg-type, return-value]


def node_rag_retrieve(state: InterviewState) -> InterviewState:
    """调用 RAG 混合检索器，注入 rag_context"""
    logger.debug(">> node_rag_retrieve")
    from rag.query_engine import query_engine

    jd = state.get("jd_parsed", {})
    query = " ".join(jd.get("tech_stack", []) + jd.get("core_competencies", []))
    if not query:
        state["rag_context"] = ""
        state["rag_sources"] = []
        return state
    results = query_engine.hybrid_query(query, top_k=10)
    state["rag_context"] = "\n---\n".join(r.get("text", "") for r in results)
    state["rag_sources"] = results
    return state


def node_plan_questions(state: InterviewState) -> InterviewState:
    logger.debug(">> node_plan_questions")
    return _question_planner.run(dict(state))  # type: ignore[arg-type, return-value]


def node_ask(state: InterviewState) -> InterviewState:
    logger.debug(">> node_ask")
    return _interviewer.run(dict(state))  # type: ignore[arg-type, return-value]


def node_evaluate_one(state: InterviewState) -> InterviewState:
    """评估单题回答，根据追问判断决定是否推进题目索引"""
    logger.debug(">> node_evaluate_one")
    from orchestration.difficulty_fsm import update_difficulty

    new_state = _evaluator.run(dict(state))
    update_difficulty(new_state)

    plan = new_state.get("question_plan", [])
    idx = new_state.get("current_question_idx", 0)

    # 如果需要追问，不推进索引
    if new_state.get("should_followup", False):
        logger.info(f"题目 {idx + 1} 需要追问，保持当前索引")
        new_state["interview_finished"] = False
        return new_state  # type: ignore[return-value]

    # 检查是否强制结束
    if new_state.get("force_finish", False):
        new_state["interview_finished"] = True
        logger.info("面试官主动判断结束面试")
        return new_state  # type: ignore[return-value]

    # 正常推进索引
    if idx + 1 >= len(plan):
        new_state["interview_finished"] = True
        logger.info(f"面试结束，共 {len(plan)} 题全部完成")
    else:
        new_state["current_question_idx"] = idx + 1
        new_state["interview_finished"] = False
        logger.info(f"推进到第 {idx + 2}/{len(plan)} 题")

    return new_state  # type: ignore[return-value]


def node_generate_report(state: InterviewState) -> InterviewState:
    logger.debug(">> node_generate_report")
    # 触发报告生成（interview_finished=True 时 evaluator 生成报告）
    return _evaluator.run(dict(state))  # type: ignore[arg-type, return-value]


def node_study_plan(state: InterviewState) -> InterviewState:
    logger.debug(">> node_study_plan")
    return _study_planner.run(dict(state))  # type: ignore[arg-type, return-value]


def node_chat(state: InterviewState) -> InterviewState:
    logger.debug(">> node_chat")
    return _chat.run(dict(state))  # type: ignore[arg-type, return-value]


def node_save_memory(state: InterviewState) -> InterviewState:
    """将本轮薄弱点写入长期记忆"""
    logger.debug(">> node_save_memory")
    from memory.memory_manager import memory_manager

    user_id = state.get("user_id", "default")
    weaknesses = state.get("weaknesses_to_remember", [])
    if weaknesses:
        memory_manager.append_weaknesses(user_id, weaknesses)
    return state


def node_load_memory(state: InterviewState) -> InterviewState:
    """加载用户长期记忆到状态"""
    logger.debug(">> node_load_memory")
    from memory.memory_manager import memory_manager

    user_id = state.get("user_id", "default")
    state["long_term_weaknesses"] = memory_manager.get_weaknesses(user_id)
    return state


def node_skill_dispatch(state: InterviewState) -> InterviewState:
    """分发到 Skill 技能系统"""
    logger.debug(">> node_skill_dispatch")
    from skills.skill_registry import skill_registry

    skill_name = state.get("skill_name", "quiz")
    skill = skill_registry.get(skill_name)
    if skill is None:
        state["agent_reply"] = f"未找到技能：{skill_name}"
        return state
    return skill.run(dict(state))  # type: ignore[arg-type, return-value]