"""
文档加载、分块、向量化入库：
- 支持 Markdown / JSON / TXT 题库
- 使用 SentenceSplitter 分块
- 向量化到 Weaviate，同时构建 BM25 倒排索引
"""
from __future__ import annotations

from pathlib import Path
from typing import List

from llama_index.core import Document, SimpleDirectoryReader
from llama_index.core.node_parser import SentenceSplitter
from llama_index.embeddings.dashscope import DashScopeEmbedding
from loguru import logger

from config import settings
from rag.retrievers.vector_retriever import get_weaviate_client


def load_documents(kb_dir: str = "rag/knowledge_base") -> List[Document]:
    """递归加载知识库目录下的所有文档"""
    kb_path = Path(kb_dir)
    if not kb_path.exists():
        logger.warning("知识库目录不存在：{}", kb_path)
        return []
    reader = SimpleDirectoryReader(
        input_dir=str(kb_path),
        recursive=True,
        required_exts=[".md", ".txt", ".json", ".pdf"],
    )
    docs = reader.load_data()
    logger.info("加载文档 {} 篇", len(docs))
    return docs


def split_documents(docs: List[Document], chunk_size: int = 512) -> List[dict]:
    """将文档切分为节点，返回节点列表"""
    splitter = SentenceSplitter(chunk_size=chunk_size, chunk_overlap=64)
    nodes = splitter.get_nodes_from_documents(docs)
    return [{"id": n.node_id, "text": n.text, "metadata": n.metadata} for n in nodes]


def build_vector_index(nodes: List[dict]) -> None:
    """将节点批量写入 Weaviate（向量索引）"""
    embed_model = DashScopeEmbedding(
        model_name=settings.embedding_model,
        api_key=settings.dashscope_api_key,
    )
    client = get_weaviate_client()

    # 创建 / 复用 Collection
    collection_name = "InterviewQuestions"
    if not client.collections.exists(collection_name):
        from weaviate.classes.config import DataType, Property

        client.collections.create(
            name=collection_name,
            properties=[
                Property(name="text", data_type=DataType.TEXT),
                Property(name="source", data_type=DataType.TEXT),
                Property(name="tech_stack", data_type=DataType.TEXT_ARRAY),
                Property(name="difficulty", data_type=DataType.TEXT),
            ],
            vectorizer_config=None,  # 使用外部 embedding
        )
        logger.info("创建 Weaviate collection: {}", collection_name)

    col = client.collections.get(collection_name)
    with col.batch.dynamic() as batch:
        for n in nodes:
            vec = embed_model.get_text_embedding(n["text"])
            meta = n.get("metadata", {}) or {}
            batch.add_object(
                properties={
                    "text": n["text"],
                    "source": meta.get("file_path", ""),
                    "tech_stack": meta.get("tech_stack", []),
                    "difficulty": meta.get("difficulty", "medium"),
                },
                vector=vec,
            )
    logger.info("向量索引写入完成：{} 条", len(nodes))


def build_full_index(kb_dir: str = "rag/knowledge_base") -> None:
    """构建完整索引：向量 + BM25"""
    docs = load_documents(kb_dir)
    nodes = split_documents(docs)
    build_vector_index(nodes)
    # BM25 索引由 BM25Retriever 运行时基于本地 JSON 构建
    from rag.retrievers.bm25_retriever import BM25Retriever

    BM25Retriever.build_corpus_cache(nodes)
    logger.success("🎉 RAG 索引构建完成")
