"""Weaviate 向量检索"""
from __future__ import annotations

from typing import Any, Dict, List

import weaviate
from llama_index.embeddings.dashscope import DashScopeEmbedding
from loguru import logger
from weaviate.classes.query import MetadataQuery

from config import settings


def get_weaviate_client() -> weaviate.WeaviateClient:
    """获取 Weaviate 客户端（单例）"""
    if settings.weaviate_api_key:
        return weaviate.connect_to_wcs(
            cluster_url=settings.weaviate_url,
            auth_credentials=weaviate.classes.init.Auth.api_key(settings.weaviate_api_key),
        )
    return weaviate.connect_to_custom(
        http_host=settings.weaviate_url.replace("http://", "").split(":")[0],
        http_port=int(settings.weaviate_url.split(":")[-1]),
        http_secure=settings.weaviate_url.startswith("https"),
        grpc_host=settings.weaviate_url.replace("http://", "").split(":")[0],
        grpc_port=50051,
        grpc_secure=False,
    )


class VectorRetriever:
    """基于 Weaviate 的向量检索"""

    def __init__(self, collection_name: str = "InterviewQuestions"):
        self.client = get_weaviate_client()
        self.collection = self.client.collections.get(collection_name)
        self.embed = DashScopeEmbedding(
            model_name=settings.embedding_model,
            api_key=settings.dashscope_api_key,
        )

    def retrieve(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """向量近邻检索"""
        query_vec = self.embed.get_query_embedding(query)
        resp = self.collection.query.near_vector(
            near_vector=query_vec,
            limit=top_k,
            return_metadata=MetadataQuery(distance=True),
        )
        results: List[Dict[str, Any]] = []
        for obj in resp.objects:
            results.append({
                "id": str(obj.uuid),
                "text": obj.properties.get("text", ""),
                "metadata": obj.properties,
                "score": 1.0 - (obj.metadata.distance or 0.0),
                "source": "vector",
            })
        logger.debug("Vector 检索 top_k={} 返回 {} 条", top_k, len(results))
        return results
