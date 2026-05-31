"""构建 RAG 向量索引"""
from loguru import logger
from rag.indexer import build_full_index


def main():
    logger.info("📚 开始构建 RAG 索引...")
    build_full_index()
    logger.success("✅ 索引构建完成")


if __name__ == "__main__":
    main()
