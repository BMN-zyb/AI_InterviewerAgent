"""
自定义评估指标：Faithfulness / Relevance / Completeness 的本地封装
"""
from __future__ import annotations

from typing import Any, Dict


def compute_faithfulness(answer: str, context: str) -> float:
    """忠实度：答案是否全部来源于 context（简化版：基于 token 重合度）"""
    if not context or not answer:
        return 0.0
    ans_tokens = set(answer.lower().split())
    ctx_tokens = set(context.lower().split())
    if not ans_tokens:
        return 0.0
    overlap = len(ans_tokens & ctx_tokens)
    return min(1.0, overlap / len(ans_tokens) * 1.5)


def compute_relevance(question: str, answer: str) -> float:
    """相关性：答案是否切题（简化版）"""
    q_tokens = set(question.lower().split())
    a_tokens = set(answer.lower().split())
    if not q_tokens:
        return 0.0
    return min(1.0, len(q_tokens & a_tokens) / len(q_tokens) * 1.2)


def compute_completeness(answer: str, reference: str) -> float:
    """完整性：相对参考答案的覆盖度"""
    if not reference:
        return 1.0 if answer else 0.0
    ref_tokens = set(reference.lower().split())
    ans_tokens = set(answer.lower().split())
    if not ref_tokens:
        return 0.0
    return min(1.0, len(ref_tokens & ans_tokens) / len(ref_tokens))


def compute_all(
    question: str, answer: str, context: str, reference: str = ""
) -> Dict[str, float]:
    return {
        "faithfulness": compute_faithfulness(answer, context),
        "relevance": compute_relevance(question, answer),
        "completeness": compute_completeness(answer, reference),
    }
