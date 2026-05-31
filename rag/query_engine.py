"""
统一查询引擎入口：
- hybrid_query: 混合检索 + RRF 融合
- full_query: 混合检索 + LLM Rerank（精排）
"""
from __future__ import annotations

from typing import Any, Dict, List

from rag.reranker import reranker
from rag.retrievers.hybrid_retriever import HybridRetriever


class QueryEngine:
    def __init__(self) -> None:
        self.hybrid = HybridRetriever()

    def hybrid_query(self, query: str, top_k: int = 10) -> List[Dict[str, Any]]:
        """仅做混合检索（快速模式）"""
        return self.hybrid.retrieve(query, top_k=top_k)

    def full_query(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """混合检索 + LLM Rerank（精排模式）"""
        candidates = self.hybrid.retrieve(query, top_k=top_k * 3)
        return reranker.rerank(query, candidates, top_k=top_k)


query_engine = QueryEngine()
