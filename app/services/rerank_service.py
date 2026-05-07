"""
重排序服务 (Rerank)
使用轻量级 Cross-Encoder 对检索结果进行精排
"""

import logging
from typing import List, Dict, Any
from sentence_transformers import CrossEncoder

logger = logging.getLogger(__name__)

# 轻量级模型：11MB，CPU 上几百毫秒
# 可选：'cross-encoder/ms-marco-MiniLM-L-6-v2' (11MB)
# 可选：'BAAI/bge-reranker-base' (1.1GB，精度更高)
MODEL_NAME = 'cross-encoder/ms-marco-MiniLM-L-6-v2'


class RerankService:
    def __init__(self):
        self.model = None

    def _load_model(self):
        """懒加载模型"""
        if self.model is None:
            logger.info(f"🚀 加载 Rerank 模型: {MODEL_NAME}")
            self.model = CrossEncoder(MODEL_NAME)
            logger.info("✅ Rerank 模型加载成功")

    def rerank(self, query: str, candidates: List[Dict], top_n: int = 1) -> List[Dict]:
        """
        对候选文档进行重排序

        Args:
            query: 用户问题
            candidates: 候选文档列表，每个元素包含 'content' 和 'metadata'
            top_n: 返回前 N 个最相关的文档

        Returns:
            重排序后的文档列表
        """
        if not candidates:
            return []

        self._load_model()

        # 准备 (query, document) 对
        pairs = [[query, doc['content']] for doc in candidates]

        # 预测相关性分数
        scores = self.model.predict(pairs)

        # 添加分数并排序
        for doc, score in zip(candidates, scores):
            doc['rerank_score'] = float(score)

        # 按分数降序排序
        candidates.sort(key=lambda x: x['rerank_score'], reverse=True)

        logger.debug(f"📊 Rerank 完成: {len(candidates)} 个候选，返回 top_{top_n}")

        return candidates[:top_n]


# 单例
_rerank_service = None


def get_rerank_service() -> RerankService:
    global _rerank_service
    if _rerank_service is None:
        _rerank_service = RerankService()
    return _rerank_service
