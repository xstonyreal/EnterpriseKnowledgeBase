# app/services/search_service.py
import os
import pickle
import jieba
import hashlib  # 新增：用於生成 chunk 的 MD5 哈希
import numpy as np
import time  # === [ADDED] 用於統計原子耗時 ===
from typing import List, Dict, Tuple, Any
from langchain_community.vectorstores import FAISS
from app.config import settings
from app.models.embeddings import embeddings
from app.core.logger import logger
from app.core.monitor import Monitor #獲取埋點數據


# 1. 向量路徑搜尋 -> 得到 vector_list
# 2. 關鍵字路徑搜尋 -> 得到 bm25_list
# 3. 遍歷這兩個 list，根據排名計算 RRF 分數
# 4. 重新排序，返回最聰明的 Top_N
class SearchService:
    # --- [單例補丁：全局靜態緩存屬性] ---
    _global_vectorstore = None
    _global_bm25_data = None
    _is_loading = False

    def __init__(self):
        # 【修改點】統一使用 Path 對象並 resolve 為絕對路徑，消除環境變量污染
        self.vector_db_path = settings.VECTOR_DB_DIR.resolve()
        self.bm25_db_path = settings.BM25_DB_DIR.resolve()

        # 優先從全局緩存同步
        self.vectorstore = SearchService._global_vectorstore
        self.bm25_data = SearchService._global_bm25_data

        # 初始化加載
        self._load_indices()

    def _load_indices(self):
        """加載雙路索引至內存"""

        # --- [單例攔截邏輯] ---
        if SearchService._global_vectorstore is not None and SearchService._global_bm25_data is not None:
            self.vectorstore = SearchService._global_vectorstore
            self.bm25_data = SearchService._global_bm25_data
            return

        # 防止多線程重複加載
        if SearchService._is_loading:
            return

        try:
            SearchService._is_loading = True

            # 【修改點】嚴格區分「目錄」與「文件」路徑
            faiss_dir = self.vector_db_path
            faiss_file = faiss_dir / "index.faiss"

            # 修正：BM25 的完整文件路徑
            bm25_file = self.bm25_db_path / "bm25.pkl"

            # 1. 加載 FAISS (如果尚未緩存)
            if SearchService._global_vectorstore is None:
                if faiss_file.exists():
                    try:
                        SearchService._global_vectorstore = FAISS.load_local(
                            str(faiss_dir),  # FAISS 需要目錄字符串
                            embeddings,
                            allow_dangerous_deserialization=True
                        )
                        logger.info(f"📡 [Search] FAISS 加載成功。絕對路徑: {faiss_file}")
                    except Exception as e:
                        logger.error(f"❌ [Search] FAISS 加載異常: {str(e)}")
                else:
                    logger.warning(f"⚠️ [Search] FAISS 文件物理缺失: {faiss_file}")

            # 2. 加載 BM25 (如果尚未緩存)
            if SearchService._global_bm25_data is None:
                if bm25_file.exists() and bm25_file.is_file():
                    try:
                        with open(bm25_file, "rb") as f:
                            SearchService._global_bm25_data = pickle.load(f)
                        logger.info(f"📡 [Search] BM25 加載成功。絕對路徑: {bm25_file}")
                    except Exception as e:
                        # 轉存錯誤消息，防止閉包 NameError
                        err_msg = str(e)
                        logger.error(f"❌ [Search] BM25 讀取異常: {err_msg}")
                    finally:
                        # 確保同步給實例
                        self.bm25_data = SearchService._global_bm25_data
                else:
                    # 如果走到這裡報 vector_db，日誌會直接抓出 settings 的現形
                    logger.error(f"❌ [Search] BM25 文件缺失。嘗試路徑: {bm25_file}")
                    logger.info(f"🔍 [Debug] 當前 settings.BM25_DB_DIR 指向: {settings.BM25_DB_DIR}")

            # 同步給實例屬性
            self.vectorstore = SearchService._global_vectorstore
            self.bm25_data = SearchService._global_bm25_data

        finally:
            SearchService._is_loading = False

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
    def _rrf_score(ranks: List[int], k: int = 60) -> float:
        """
        RRF (Reciprocal Rank Fusion) 核心算法
        原理：得分 = 1 / (k + 排名)
        """
        score = 0.0
        for rank in ranks:
            score += 1.0 / (k + rank)
        return score

    def hybrid_search(self, query: str, top_n: int = 5) -> Tuple[List[Dict], Dict[str, Any]]:
        """
        【核心】混合檢索入口,加入了懶加載（Lazy Loading）機制，防止冷啟動或同步後未及時加載的問題
        """
        """
        混合檢索入口，增加性能埋點與原子觀測指標
        """
        metrics = {
            "vector_count": 0,
            "bm25_count": 0,
            "vector_ms": 0,
            "bm25_ms": 0,
            "fusion_count": 0
        }
        # 如果內存中索引為空，嘗試即時觸發一次加載（自動補救）
        if not self.vectorstore or not self.bm25_data:
            logger.warning("⚠️ 索引未就緒，回退至單路搜索或報錯。")
            self._load_indices()

        # 再次檢查，若仍加載失敗則回退，避免後續邏輯報錯
        if not self.vectorstore:
            logger.warning("⚠️ 索引加載失敗，無法執行檢索，請檢查索引文件是否已生成。")
            return [], metrics

        # --- 第一路：向量檢索 ---
        s1 = time.perf_counter()
        vector_results = self.vectorstore.similarity_search_with_relevance_scores(query, k=top_n * 2)
        metrics["vector_ms"] = int((time.perf_counter() - s1) * 1000)
        metrics["vector_count"] = len(vector_results)

        # --- 第二路：BM25 檢索 (作為增強) ---
        s2 = time.perf_counter()
        top_n_indices = []
        bm25_docs = []

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

        metrics["bm25_ms"] = int((time.perf_counter() - s2) * 1000)
        metrics["bm25_count"] = len(top_n_indices)

        # 3. 系統性埋點輸出
        Monitor.log_metrics(
            module="Search",
            action="hybrid_retrieval",
            metrics={
                "v_ms": metrics["vector_ms"],
                "b_ms": metrics["bm25_ms"],
                "total_ms": metrics["vector_ms"] + metrics["bm25_ms"]
            },
            extra={"q_len": len(query), "hits": len(vector_results)}
        )

        # --- 第三路：RRF 融合 ---
        all_docs = {}  # 用於存放融合後的結果

        for rank, (doc, _) in enumerate(vector_results):
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

        metrics["fusion_count"] = len(final_results)

        output = [{"content": doc.page_content, "metadata": doc.metadata, "score": score}
                  for doc, score in final_results[:top_n]]


        # === [系統性埋點：本地日誌持久化] ===
        import json
        metrics_payload = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "query": query[:50],  # 記錄脫敏後的查詢內容前 50 字
            "top_k": top_n,
            "latency": {
                "vector_ms": metrics["vector_ms"],
                "bm25_ms": metrics["bm25_ms"],
                "total_retrieval_ms": metrics["vector_ms"] + metrics["bm25_ms"]
            },
            "counts": {
                "vector": metrics["vector_count"],
                "bm25": metrics["bm25_count"],
                "fusion": metrics["fusion_count"]
            }
        }

        # 使用特定標籤輸出，確保數據可被系統化解析
        logger.info(f"📊 [METRICS] {json.dumps(metrics_payload, ensure_ascii=False)}")
        # =================================
        return output, metrics