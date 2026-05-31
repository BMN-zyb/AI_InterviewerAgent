"""
LangGraph 主面试流程 DAG 定义（StateGraph）
"""
from __future__ import annotations

from functools import lru_cache

from langgraph.graph import END, START, StateGraph

from orchestration.edges import (
    route_after_evaluate,
    route_after_jd,
    route_after_plan,
    route_after_report,
    route_after_resume,
    route_by_intent,
)
from orchestration.nodes import (
    node_ask,
    node_chat,
    node_evaluate_one,
    node_generate_report,
    node_jd_analyze,
    node_load_memory,
    node_plan_questions,
    node_rag_retrieve,
    node_resume_analyze,
    node_route,
    node_save_memory,
    node_skill_dispatch,
    node_study_plan,
)
from orchestration.state import InterviewState


def build_interview_graph() -> StateGraph:
    graph = StateGraph(InterviewState)

    # 注册所有节点
    graph.add_node("route", node_route)
    graph.add_node("jd_analyze", node_jd_analyze)
    graph.add_node("resume_analyze", node_resume_analyze)
    graph.add_node("rag_retrieve", node_rag_retrieve)
    graph.add_node("plan_questions", node_plan_questions)
    graph.add_node("ask", node_ask)
    graph.add_node("evaluate_one", node_evaluate_one)
    graph.add_node("generate_report", node_generate_report)
    graph.add_node("study_plan", node_study_plan)
    graph.add_node("chat", node_chat)
    graph.add_node("skill_dispatch", node_skill_dispatch)
    graph.add_node("load_memory", node_load_memory)
    graph.add_node("save_memory", node_save_memory)

    # 入口 -> 路由
    graph.add_edge(START, "route")

    # 路由分流
    graph.add_conditional_edges(
        "route",
        route_by_intent,
        {
            "load_memory": "load_memory",
            "jd_analyze": "jd_analyze",
            "resume_analyze": "resume_analyze",
            "rag_retrieve": "rag_retrieve",
            "evaluate_one": "evaluate_one",
            "skill_dispatch": "skill_dispatch",
            "chat": "chat",
        },
    )

    # 面试启动链路
    graph.add_edge("load_memory", "jd_analyze")
    graph.add_conditional_edges(
        "jd_analyze",
        route_after_jd,
        {"resume_analyze": "resume_analyze", "rag_retrieve": "rag_retrieve"},
    )
    graph.add_conditional_edges(
        "resume_analyze",
        route_after_resume,
        {"rag_retrieve": "rag_retrieve", "chat": "chat"},
    )
    graph.add_edge("rag_retrieve", "plan_questions")
    graph.add_conditional_edges(
        "plan_questions",
        route_after_plan,
        {"ask": "ask", "chat": "chat"},
    )
    graph.add_edge("ask", END)  # 挂起等用户回答

    # 答题评估循环 (追问也会回到 ask)
    graph.add_conditional_edges(
        "evaluate_one",
        route_after_evaluate,
        {"ask": "ask", "generate_report": "generate_report"},
    )

    # 面试结束链路
    graph.add_conditional_edges(
        "generate_report",
        route_after_report,
        {"study_plan": "study_plan"},
    )
    graph.add_edge("study_plan", "save_memory")
    graph.add_edge("save_memory", END)

    # 其他出口
    graph.add_edge("chat", END)
    graph.add_edge("skill_dispatch", END)

    return graph


@lru_cache
def get_compiled_graph():
    return build_interview_graph().compile()