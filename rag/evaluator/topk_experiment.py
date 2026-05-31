"""
TopK 调优实验脚本：
对比 top_k = 3, 5, 10, 20 下的 RAG 评估分数，找出最优 K
"""
from __future__ import annotations

import json
from pathlib import Path

from loguru import logger

from rag.evaluator.rag_evaluator import RAGEvaluator
from rag.query_engine import query_engine

EVAL_SET_PATH = Path("data/rag_eval_set.json")


def run_topk_experiment(top_k_list: list[int] = (3, 5, 10, 20)) -> dict:
    if not EVAL_SET_PATH.exists():
        logger.error("评估集不存在：{}", EVAL_SET_PATH)
        return {}

    with open(EVAL_SET_PATH, "r", encoding="utf-8") as f:
        eval_set = json.load(f)  # [{question, ground_truth}]

    evaluator = RAGEvaluator()
    results: dict = {}
    for k in top_k_list:
        questions, answers, contexts = [], [], []
        for item in eval_set:
            q = item["question"]
            ctx = query_engine.full_query(q, top_k=k)
            ctx_texts = [c["text"] for c in ctx]
            # 简化：使用第一条 context 作为回答基础（真实场景应让 LLM 生成）
            answers.append(" ".join(ctx_texts)[:1000])
            contexts.append(ctx_texts)
            questions.append(q)

        scores = evaluator.evaluate(questions, answers, contexts)
        results[f"top_{k}"] = scores
        logger.info("top_k={} => {}", k, scores)

    # 保存
    Path("data/experiment_results.json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return results


if __name__ == "__main__":
    print(run_topk_experiment())
