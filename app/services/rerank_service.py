# app/services/rerank_service.py
"""
重排序服务 (Rerank)
使用轻量级 Cross-Encoder 对检索结果进行精排
"""
import os
from sentence_transformers import CrossEncoder

# 項目內部導入
from app.config import settings
from app.core.logger import logger


class RerankService:
    """
    Matrix Intelligence 精排服務
    智能加載策略：本地路徑優先 -> 網絡備選 -> 自動本地化存檔
    """

    # --- 關鍵繼承性改造：類級別的全局緩存 ---
    _shared_model = None

    def __init__(self):
        self.model = None
        self.model_name = settings.RERANK_MODEL_NAME
        self.local_path = settings.RERANK_MODEL_PATH

        if settings.ENABLE_RERANK:
            # 只有當共享模型為空時才初始化
            if RerankService._shared_model is None:
                self._initialize_engine()
                RerankService._shared_model = self.model
            else:
                # 否則直接繼承已有的模型實例
                self.model = RerankService._shared_model
                logger.debug("♻️ [RerankService] 復用已加載的模型實例")

    def _initialize_engine(self):
        try:
            logger.info("🎯 [RerankService] 啟動智能加載程序...")

            # 1. 確保目錄存在且進行物理路徑歸一化
            self.local_path.parent.mkdir(parents=True, exist_ok=True)
            local_abs_path = self.local_path.resolve()

            # 2. 探測本地鎖定目錄是否有效 (必須存在且包含模型文件)
            is_local_valid = local_abs_path.exists() and (local_abs_path / "config.json").exists()

            if is_local_valid:
                logger.info(f"✅ 發現本地鎖定模型: {local_abs_path}")
                os.environ["HF_HUB_OFFLINE"] = "1"
                os.environ["TRANSFORMERS_OFFLINE"] = "1"
                load_source = str(local_abs_path)
            else:
                logger.warning(f"⚠️ 本地鎖定路徑缺失核心文件，準備執行首次同步...")
                os.environ["HF_HUB_OFFLINE"] = "0"
                os.environ["TRANSFORMERS_OFFLINE"] = "0"
                load_source = self.model_name

            # 3. 執行物理加載
            self.model = CrossEncoder(
                load_source,
                max_length=512,
                device="cpu"
            )

            # 4. 首次下載存檔
            if not is_local_valid:
                logger.info(f"💾 正在執行一次性物理歸檔至: {local_abs_path}")
                local_abs_path.mkdir(parents=True, exist_ok=True)
                self.model.save(str(local_abs_path))
                os.environ["HF_HUB_OFFLINE"] = "1"
                os.environ["TRANSFORMERS_OFFLINE"] = "1"
                logger.info("✨ 模型已成功鎖定在本地。")

            logger.info("✅ [RerankService] 精排引擎加載就緒。")

        except Exception as e:
            logger.error(f"❌ 精排引擎初始化異常: {e}")
            self.model = None

    def rerank(self, query: str, documents: list, top_n: int = 5) -> list:
        if not self.model or not documents:
            return documents[:top_n]

        try:
            sentence_pairs = [[query, doc.get("content", "")] for doc in documents]
            scores = self.model.predict(sentence_pairs)
            for i, doc in enumerate(documents):
                doc["rerank_score"] = float(scores[i])
            return sorted(documents, key=lambda x: x["rerank_score"], reverse=True)[:top_n]
        except Exception as e:
            logger.error(f"❌ Rerank 計算過程異常: {e}")
            return documents[:top_n]


# ---------------------------------------------------------
# 5. 模塊級單例導出 (保留原有接口)
# ---------------------------------------------------------
rerank_service = RerankService()

# 【新增】為了解決 engine.py 調用 get_rerank_service() 報錯的問題
def get_rerank_service():
    """獲取 Rerank 服務單例"""
    global rerank_service
    # 如果因為某種原因初始化失敗，嘗試重新加載
    if rerank_service.model is None and settings.ENABLE_RERANK:
        rerank_service = RerankService()
    return rerank_service