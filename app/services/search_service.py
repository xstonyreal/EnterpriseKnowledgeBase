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
        # 【修改點】統一使用 Path 對象並 resolve 為絕對路徑，消除環境變量污染
        self.vector_db_path = settings.VECTOR_DB_DIR.resolve()
        self.bm25_db_path = settings.BM25_DB_DIR.resolve()

        self.vectorstore = None
        self.bm25_data = None

        # 初始化加載
        self._load_indices()

    def _load_indices(self):
        """加載雙路索引至內存"""
        """加載雙路索引至內存"""
        # 【修改點】嚴格區分「目錄」與「文件」路徑
        faiss_dir = self.vector_db_path
        faiss_file = faiss_dir / "index.faiss"

        # 修正：BM25 的完整文件路徑
        bm25_file = self.bm25_db_path / "bm25.pkl"

        # 1. 加載 FAISS
        if faiss_file.exists():
            try:
                self.vectorstore = FAISS.load_local(
                    str(faiss_dir),  # FAISS 需要目錄字符串
                    embeddings,
                    allow_dangerous_deserialization=True
                )
                logger.info(f"📡 [Search] FAISS 加載成功。絕對路徑: {faiss_file}")
            except Exception as e:
                logger.error(f"❌ [Search] FAISS 加載異常: {str(e)}")
        else:
            logger.warning(f"⚠️ [Search] FAISS 文件物理缺失: {faiss_file}")

        # 2. 加載 BM25
        # 【修改點】使用剛才定義的 bm25_file (文件路徑)，而不是 self.bm25_db_path (目錄路徑)
        bm25_file = self.bm25_db_path / "bm25.pkl"
        if bm25_file.exists() and bm25_file.is_file():
            try:
                with open(bm25_file, "rb") as f:
                    self.bm25_data = pickle.load(f)
                logger.info(f"📡 [Search] BM25 加載成功。絕對路徑: {bm25_file}")
            except Exception as e:
                # 轉存錯誤消息，防止閉包 NameError
                err_msg = str(e)
                logger.error(f"❌ [Search] BM25 讀取異常: {err_msg}")
                self.bm25_data = None
        else:
            # 如果走到這裡報 vector_db，日誌會直接抓出 settings 的現形
            logger.error(f"❌ [Search] BM25 文件缺失。嘗試路徑: {bm25_file}")
            logger.info(f"🔍 [Debug] 當前 settings.BM25_DB_DIR 指向: {settings.BM25_DB_DIR}")
            self.bm25_data = None

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
        【核心】混合檢索入口,加入了懶加載（Lazy Loading）機制，防止冷啟動或同步後未及時加載的問題
        """
        # 如果內存中索引為空，嘗試即時觸發一次加載（自動補救）
        if not self.vectorstore or not self.bm25_data:
            logger.warning("⚠️ 索引未就緒，回退至單路搜索或報錯。")
            self._load_indices()

        # 再次檢查，若仍加載失敗則回退，避免後續邏輯報錯
        if not self.vectorstore:
            logger.warning("⚠️ 索引加載失敗，無法執行檢索，請檢查索引文件是否已生成。")
            return []

        # --- 第一路：向量檢索 ---
        # 返回 (Document, Score)
        vector_results = self.vectorstore.similarity_search_with_relevance_scores(query, k=top_n * 2)

        # --- 第二路：BM25 檢索 (作為增強) ---
        # 【修改點】將 BM25 邏輯完全包裹在狀態檢查中
        top_n_indices = []
        bm25_docs = []

        # 獲取 BM25 得分並排序

        # 【修正點】增加判斷，防止 NoneType 報錯
        if self.bm25_data is not None and isinstance(self.bm25_data, dict):
            try:
                tokenized_query = jieba.lcut_for_search(query)
                bm25_instance = self.bm25_data.get("instance")
                bm25_docs = self.bm25_data.get("documents", [])

                if bm25_instance:
                    doc_scores = bm25_instance.get_scores(tokenized_query)
                    top_n_indices = np.argsort(doc_scores)[::-1][:top_n * 2]
            except Exception as e:
                logger.error(f"⚠️ [Search] BM25 檢索異常: {str(e)}")
        else:
            logger.warning("⚠️ BM25 數據不可用，本次僅使用向量路。")

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