"""
RAG 质量评估：基于 RAGAS 的三维评估
- Faithfulness（忠实度）
- Answer Relevancy（相关性）
- Completeness（完整性）
"""
from __future__ import annotations

from typing import Any, Dict, List

from loguru import logger


class RAGEvaluator:
    """RAG 质量评估器（封装 RAGAS）"""

    def __init__(self) -> None:
        self._metrics_loaded = False

    def _load_metrics(self) -> None:
        if self._metrics_loaded:
            return
        try:
            from ragas.metrics import answer_relevancy, context_precision, faithfulness
            from ragas.metrics.critique import harmfulness

            self.metrics = [faithfulness, answer_relevancy, context_precision]
            self._metrics_loaded = True
            logger.info("RAGAS 指标加载完成")
        except ImportError as e:
            logger.error("ragas 未安装: {}", e)
            self.metrics = []
            self._metrics_loaded = True

    def evaluate(
        self,
        questions: List[str],
        answers: List[str],
        contexts: List[List[str]],
        ground_truths: List[str] | None = None,
    ) -> Dict[str, float]:
        """运行 RAGAS 评估，返回各指标均值"""
        self._load_metrics()
        if not self.metrics:
            return {}

        from datasets import Dataset
        from ragas import evaluate as ragas_evaluate

        ds = Dataset.from_dict({
            "question": questions,
            "answer": answers,
            "contexts": contexts,
            "ground_truth": ground_truths or [""] * len(questions),
        })
        result = ragas_evaluate(ds, metrics=self.metrics)
        scores: Dict[str, float] = {}
        df = result.to_pandas()
        for col in df.columns:
            if col in ("question", "answer", "contexts", "ground_truth"):
                continue
            scores[col] = float(df[col].mean())
        logger.info("RAG 评估结果：{}", scores)
        return scores

    def evaluate_single(
        self, question: str, answer: str, context: str
    ) -> Dict[str, float]:
        """单条评估"""
        return self.evaluate(
            [question], [answer], [[context]]
        )
