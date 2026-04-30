# app/services/search_service.py
import os
import pickle
import jieba
import hashlib  # 新增：用於生成 chunk 的 MD5 哈希
import numpy as np
from typing import List, Dict
from langchain_community.vectorstores import FAISS
from app.config import settings
from app.models.embeddings import embeddings
from app.core.logger import logger

# 1. 向量路徑搜尋 -> 得到 vector_list
# 2. 關鍵字路徑搜尋 -> 得到 bm25_list
# 3. 遍歷這兩個 list，根據排名計算 RRF 分數
# 4. 重新排序，返回最聰明的 Top_N
class SearchService:
    def __init__(self):
        self.vector_db_path = settings.VECTOR_DB_DIR
        self.bm25_db_path = os.path.join(settings.BM25_DB_DIR, "bm25.pkl")
        self.vectorstore = None
        self.bm25_data = None

        # 初始化加載
        self._load_indices()

    def _load_indices(self):
        """加載雙路索引至內存"""
        # 1. 加載 FAISS
        if os.path.exists(os.path.join(self.vector_db_path, "index.faiss")):
            self.vectorstore = FAISS.load_local(
                self.vector_db_path,
                embeddings,
                allow_dangerous_deserialization=True
            )
            logger.info("📡 [Search] FAISS 向量庫加載成功。")

        # 2. 加載 BM25
        if os.path.exists(self.bm25_db_path):
            with open(self.bm25_db_path, "rb") as f:
                self.bm25_data = pickle.load(f)
            logger.info("📡 [Search] BM25 關鍵字庫加載成功。")

    @staticmethod
    def _get_chunk_id(source: str, content: str, prefix: str = "") -> str:
        """
        為 chunk 生成唯一 ID（基於內容 MD5 哈希）

        參數:
            source: 來源文件路徑
            content: chunk 的完整內容
            prefix: 前綴（可選，用於調試）

        返回:
            唯一標識符，格式: {source}_{content_md5}
        """
        content_hash = hashlib.md5(content.encode()).hexdigest()
        return f"{prefix}{source}_{content_hash}" if prefix else f"{source}_{content_hash}"

    @staticmethod
    def _rrf_score( ranks: List[int], k: int = 60) -> float:
        """
        RRF (Reciprocal Rank Fusion) 核心算法
        原理：得分 = 1 / (k + 排名)
        """
        score = 0.0
        for rank in ranks:
            score += 1.0 / (k + rank)
        return score

    def hybrid_search(self, query: str, top_n: int = 5) -> List[Dict]:
        """
        【核心】混合檢索入口
        """
        if not self.vectorstore or not self.bm25_data:
            logger.warning("⚠️ 索引未就緒，回退至單路搜索或報錯。")
            return []

        # --- 第一路：向量檢索 ---
        # 返回 (Document, Score)
        vector_results = self.vectorstore.similarity_search_with_relevance_scores(query, k=top_n * 2)

        # --- 第二路：BM25 檢索 ---
        tokenized_query = jieba.lcut_for_search(query)
        bm25_instance = self.bm25_data["instance"]
        bm25_docs = self.bm25_data["documents"]

        # 獲取 BM25 得分並排序
        doc_scores = bm25_instance.get_scores(tokenized_query)
        top_n_indices = np.argsort(doc_scores)[::-1][:top_n * 2]

        # --- 第三路：RRF 融合 ---
        all_docs = {}  # 用於存放融合後的結果

        # 處理向量排名
        for rank, (doc, _) in enumerate(vector_results):
            # 修改點：doc_id 原本使用 doc.page_content（可能導致不同文件內容相同時錯誤合併）
            # 改為使用 "來源檔名_排名_內容前50字" 作為唯一識別碼
            # .get('source', 'unknown') 中的 'unknown' 是防呆預設值，當 metadata 中沒有 source 鍵時使用
            # ============================================================
            # 【優化方案記錄】doc_id 生成邏輯（當前保留原始代碼）by DS
            # ============================================================
            # 問題：當前使用 doc.page_content[:50] 可能洩露隱私，且兩路檢索 ID 不一致
            # 建議改進：使用內容 MD5 哈希值作為唯一標識
            #
            # 改進後代碼示例（僅供參考，當前未啟用）：
            # import hashlib
            # content_hash = hashlib.md5(doc.page_content.encode()).hexdigest()
            # doc_id = f"vec_{doc.metadata.get('source', 'unknown')}_{content_hash}"
            #
            # 優點：
            # 1. 不洩露原始內容（哈希不可逆）
            # 2. 同一 chunk 在向量和 BM25 中 ID 一致，可正確融合
            # 3. 與項目中 hash_utils.py 的 MD5 指紋邏輯保持一致
            # ============================================================
            # 使用基於 MD5 的唯一 ID，不再包含內容原文和前綴區分
            # doc_id = f"vec_{doc.metadata.get('source', 'unknown')}_{rank}_{doc.page_content[:50]}" # 使用內容作為唯一標識，或使用 metadata 中的 source
            doc_id = self._get_chunk_id(
                source=doc.metadata.get('source', 'unknown'),
                content=doc.page_content
            )
            if doc_id not in all_docs:
                all_docs[doc_id] = {"doc": doc, "ranks": []}
            all_docs[doc_id]["ranks"].append(rank + 1)

        # 處理 BM25 排名
        for rank, idx in enumerate(top_n_indices):
            doc = bm25_docs[idx]
            # ============================================================
            # 【優化方案記錄】同上，doc_id 生成邏輯待優化
            # 改進後應與向量檢索使用相同的哈希計算方式，確保 ID 一致
            # ============================================================
            doc_id = self._get_chunk_id(
                source=doc.metadata.get('source', 'unknown'),
                content=doc.page_content
            )
            if doc_id not in all_docs:
                all_docs[doc_id] = {"doc": doc, "ranks": []}
            all_docs[doc_id]["ranks"].append(rank + 1)

        # 計算最終 RRF 得分並排序
        final_results = []
        for doc_id, data in all_docs.items():
            rrf_score = self._rrf_score(data["ranks"])
            final_results.append((data["doc"], rrf_score))

        # 按 RRF 得分降序排列
        final_results.sort(key=lambda x: x[1], reverse=True)

        return [{"content": doc.page_content, "metadata": doc.metadata, "score": score}
                for doc, score in final_results[:top_n]]