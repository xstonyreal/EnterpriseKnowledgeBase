# app/services/search_service.py
import os
import pickle
import jieba
import hashlib
import numpy as np
from typing import List, Dict, Optional
from langchain_community.vectorstores import FAISS
from app.config import settings
from app.models.embeddings import embeddings
from app.core.logger import logger


class SearchService:
    def __init__(self):
        self.vector_db_path = settings.VECTOR_DB_DIR
        self.bm25_db_path = os.path.join(settings.BM25_DB_DIR, "bm25.pkl")
        self.vectorstore = None
        self.bm25_data = None

        # 初始化加載索引
        self._load_indices()

    def _load_indices(self):
        """加載雙路索引至內存（向量 + 關鍵字）"""
        try:
            # 1. 加載 FAISS
            if os.path.exists(os.path.join(self.vector_db_path, "index.faiss")):
                self.vectorstore = FAISS.load_local(
                    self.vector_db_path,
                    embeddings,
                    allow_dangerous_deserialization=True
                )
                logger.info("📡 [SearchService] FAISS 向量庫加載成功。")
            else:
                logger.warning(f"⚠️ [SearchService] 向量庫路徑不存在: {self.vector_db_path}")

            # 2. 加載 BM25
            if os.path.exists(self.bm25_db_path):
                with open(self.bm25_db_path, "rb") as f:
                    self.bm25_data = pickle.load(f)
                logger.info("📡 [SearchService] BM25 關鍵字庫加載成功。")
            else:
                logger.warning(f"⚠️ [SearchService] BM25 庫路徑不存在: {self.bm25_db_path}")
        except Exception as e:
            logger.error(f"🚨 [SearchService] 加載索引失敗: {e}")

    @staticmethod
    def _get_chunk_id(source: str, content: str) -> str:
        """為 chunk 生成唯一 ID，用於 RRF 融合對齊"""
        content_hash = hashlib.md5(content.encode()).hexdigest()
        return f"{source}_{content_hash}"

    @staticmethod
    def _rrf_score(ranks: List[int], k: int = 60) -> float:
        """RRF (Reciprocal Rank Fusion) 核心算法"""
        score = 0.0
        for rank in ranks:
            score += 1.0 / (k + rank)
        return score

    def hybrid_search(self, query: str, domain: Optional[str] = None, top_n: int = 5) -> List[Dict]:
        """
        【核心】混合檢索入口
        支持語義向量 + BM25 關鍵詞，並通過 RRF 算法融合
        """
        if not self.vectorstore or not self.bm25_data:
            logger.warning("⚠️ 索引未就緒，嘗試單獨檢索或報錯。")
            return []

        # --- 第一路：向量檢索 (Vector Search) ---
        # 這裡直接注入分域過濾 (Metadata Filter)
        search_kwargs = {"k": top_n * 2}
        if domain and domain != "全局":
            search_kwargs["filter"] = {"domain": domain}

        vector_results = self.vectorstore.similarity_search_with_relevance_scores(
            query,
            **search_kwargs
        )

        # --- 第二路：BM25 檢索 (Keyword Search) ---
        tokenized_query = jieba.lcut_for_search(query)
        bm25_instance = self.bm25_data["instance"]
        bm25_docs = self.bm25_data["documents"]

        # 計算 BM25 得分
        doc_scores = bm25_instance.get_scores(tokenized_query)

        # 過濾邏輯：如果指定了域，只考慮該域下的文檔
        eligible_indices = []
        for i, doc in enumerate(bm25_docs):
            if not domain or domain == "全局" or doc.metadata.get("domain") == domain:
                eligible_indices.append(i)

        # 在符合域條件的文檔中進行排名
        if not eligible_indices:
            top_bm25_indices = []
        else:
            # 僅對 eligible_indices 的分數進行排序
            sub_scores = doc_scores[eligible_indices]
            # 獲取相對位置的 top_n
            relative_top_n = np.argsort(sub_scores)[::-1][:top_n * 2]
            # 映射回全局索引
            top_bm25_indices = [eligible_indices[idx] for idx in relative_top_n]

        # --- 第三路：RRF 融合 (Reciprocal Rank Fusion) ---
        all_docs = {}

        # 處理向量排名得分 (Rank 1 開始)
        for rank, (doc, _) in enumerate(vector_results):
            doc_id = self._get_chunk_id(doc.metadata.get('source', 'unknown'), doc.page_content)
            if doc_id not in all_docs:
                all_docs[doc_id] = {"doc": doc, "ranks": []}
            all_docs[doc_id]["ranks"].append(rank + 1)

        # 處理 BM25 排名得分
        for rank, idx in enumerate(top_bm25_indices):
            doc = bm25_docs[idx]
            doc_id = self._get_chunk_id(doc.metadata.get('source', 'unknown'), doc.page_content)
            if doc_id not in all_docs:
                all_docs[doc_id] = {"doc": doc, "ranks": []}
            all_docs[doc_id]["ranks"].append(rank + 1)

        # 計算融合後的 RRF 得分
        final_results = []
        for doc_id, data in all_docs.items():
            score = self._rrf_score(data["ranks"])
            final_results.append((data["doc"], score))

        # 按總分降序排序
        final_results.sort(key=lambda x: x[1], reverse=True)

        # 封裝結果返回
        return [
            {
                "content": doc.page_content,
                "metadata": doc.metadata,
                "score": score
            }
            for doc, score in final_results[:top_n]
        ]


# ============================================================
# 【工程化出口】
# 實例化單例並暴露簡單的函數接口，供 chat.py 調用
# ============================================================

_service = SearchService()


def do_hybrid_search(query: str, domain: str = None, top_k: int = 5):
    """
    對外封裝接口：供問答鏈條調用的純淨函數
    """
    return _service.hybrid_search(query, domain=domain, top_n=top_k)