"""
混合检索器：向量 + BM25 双路并行，RRF 融合去重
"""
from __future__ import annotations

from typing import Any, Dict, List

from loguru import logger

from config import settings
from rag.retrievers.bm25_retriever import BM25Retriever
from rag.retrievers.vector_retriever import VectorRetriever


def reciprocal_rank_fusion(
    vector_results: List[Dict[str, Any]],
    bm25_results: List[Dict[str, Any]],
    *,
    vector_weight: float = 0.6,
    bm25_weight: float = 0.4,
    k: int = 60,
) -> List[Dict[str, Any]]:
    """RRF 融合：score = w1/(k+rank1) + w2/(k+rank2)"""
    score_map: Dict[str, Dict[str, Any]] = {}

    for rank, r in enumerate(vector_results):
        rid = r["id"]
        score_map.setdefault(rid, {"doc": r, "rrf": 0.0})
        score_map[rid]["rrf"] += vector_weight / (k + rank + 1)

    for rank, r in enumerate(bm25_results):
        rid = r["id"]
        score_map.setdefault(rid, {"doc": r, "rrf": 0.0})
        score_map[rid]["rrf"] += bm25_weight / (k + rank + 1)

    merged = sorted(score_map.values(), key=lambda x: x["rrf"], reverse=True)
    return [{"id": m["doc"]["id"], "text": m["doc"]["text"],
             "metadata": m["doc"].get("metadata", {}),
             "score": m["rrf"], "source": "hybrid"} for m in merged]


class HybridRetriever:
    """向量 + BM25 双路混合检索"""

    def __init__(self) -> None:
        self.vector = VectorRetriever()
        self.bm25 = BM25Retriever()

    def retrieve(self, query: str, top_k: int | None = None) -> List[Dict[str, Any]]:
        top_k = top_k or settings.rag_top_k
        vec_results = self.vector.retrieve(query, top_k=top_k * 2)
        bm25_results = self.bm25.retrieve(query, top_k=top_k * 2)
        logger.debug("Hybrid: vec={} bm25={}", len(vec_results), len(bm25_results))
        merged = reciprocal_rank_fusion(
            vec_results,
            bm25_results,
            vector_weight=settings.rag_vector_weight,
            bm25_weight=settings.rag_bm25_weight,
        )
        return merged[:top_k]
