"""
RAG Debug Test - Full Pipeline Visibility
"""

from rag.retrievers.bm25_retriever import BM25Retriever
from rag.retrievers.vector_retriever import VectorRetriever
from rag.retrievers.hybrid_retriever import HybridRetriever
from rag.reranker import LLMReranker  # LLMReranker 单例

from rag.evaluator.metrics import compute_all

reranker = LLMReranker()



def test_metrics_basic():
    scores = compute_all(
        question="什么是 Python GIL？",
        answer="GIL 是全局解释器锁，限制同一时刻只有一个线程执行 Python 字节码",
        context="GIL（Global Interpreter Lock）是 CPython 中的一个互斥锁",
        reference="GIL 是全局解释器锁，限制同一时刻只有一个线程执行 Python 字节码",
    )

    print("scores:", scores)

    assert 0 <= scores["faithfulness"] <= 1
    assert 0 <= scores["relevance"] <= 1
    assert 0 <= scores["completeness"] <= 1




# =========================
# 选择 retriever
# =========================
def build_retriever(mode="hybrid"):
    if mode == "bm25":
        return BM25Retriever()
    elif mode == "vector":
        return VectorRetriever()
    elif mode == "hybrid":
        return HybridRetriever()
    else:
        raise ValueError(f"Unknown mode: {mode}")


# =========================
# Debug Pipeline
# =========================
def run_rag_debug(query: str, top_k=5, mode="hybrid"):
    print("\n" + "=" * 60)
    print("🔍 QUERY:", query)
    print("📦 RETRIEVER:", mode)
    print("=" * 60)

    retriever = build_retriever(mode)

    # 1. 召回
    candidates = retriever.retrieve(query, top_k=top_k * 3)

    print("\n📌 [1. RETRIEVAL - BEFORE RERANK]")
    for i, c in enumerate(candidates):
        print(f"{i+1}. id={c['id']} | text={c['text'][:80]}")

    # 2. LLM rerank
    reranked = reranker.rerank(query, candidates, top_k=top_k)

    print("\n📌 [2. RERANK - AFTER LLM RERANK]")
    for i, c in enumerate(reranked):
        print(f"{i+1}. id={c['id']} | text={c['text'][:80]}")

    # 3. 构造 context
    context = "\n".join([c["text"] for c in reranked])

    print("\n📌 [3. FINAL CONTEXT -> LLM]")
    print(context)

    # 4. mock answer / reference（你可以换真实生成结果）
    answer = reranked[0]["text"] if reranked else ""
    reference = answer

    # 5. evaluator
    scores = compute_all(
        question=query,
        answer=answer,
        context=context,
        reference=reference,
    )

    print("\n📊 [4. EVALUATION]")
    print(scores)

    return {
        "query": query,
        'answer': answer,
        "retrieved": candidates,
        "reranked": reranked,
        "context": context,
        "scores": scores,
    }


# =========================
# CLI test
# =========================
if __name__ == "__main__":
    test1 = run_rag_debug(
        "Transformer的位置编码为什么用正弦余弦函数，而不是直接学习一个位置embedding？",
        top_k=3,
        mode="hybrid"
    )

    print("\n" + "=" * 60)
    print("test reference answer:", test1['answer'])
    print("=" * 60)

    test_metrics_basic()

