"""
LLM Reranker：使用大模型对候选文档做精排
比传统 cross-encoder 更灵活，能针对具体 query 判断相关性
"""
from __future__ import annotations

from typing import Any, Dict, List

from loguru import logger

from agents.base_agent import BaseAgent

RERANK_PROMPT = """你是相关性评估专家。针对用户 Query，对以下候选文档按相关性从高到低排序。
只需返回排序后的 id 列表（JSON 数组），不要多余文字。

Query: {query}

候选文档：
{docs}

输出格式：["id1", "id2", ...]
"""


class LLMReranker(BaseAgent):
    name = "llm_reranker"

    def rerank(
        self, query: str, candidates: List[Dict[str, Any]], top_k: int = 5
    ) -> List[Dict[str, Any]]:
        if not candidates:
            return []
        docs_text = "\n".join(
            f"[{c['id']}] {c['text'][:300]}" for c in candidates[:20]
        )
        try:
            parsed = self.invoke_llm_json(
                RERANK_PROMPT.format(query=query, docs=docs_text), ""
            )
            if isinstance(parsed, list):
                ordered_ids = parsed
            else:
                ordered_ids = parsed.get("order", parsed.get("ids", []))
        except Exception as e:
            logger.warning("Reranker 失败，保持原序: {}", e)
            return candidates[:top_k]

        id_to_doc = {c["id"]: c for c in candidates}
        reranked: List[Dict[str, Any]] = []
        for rid in ordered_ids:
            if rid in id_to_doc:
                reranked.append(id_to_doc[rid])
        # 兜底：补充未被排序的
        for c in candidates:
            if c["id"] not in [r["id"] for r in reranked]:
                reranked.append(c)
        return reranked[:top_k]
    

    # def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
    #     query = state.get("query", "")
    #     candidates = state.get("candidates", [])
    #     top_k = state.get("top_k", 5)

    #     reranked = self.rerank(query, candidates, top_k)

    #     return {
    #         **state,
    #         "candidates": reranked,
    #     }


    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        # reranker 不走 graph node，这里做兼容占位
        return state

reranker = LLMReranker()
