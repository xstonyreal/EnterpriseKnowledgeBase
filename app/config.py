# app/config.py

import os
from typing import ClassVar, Optional, List
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator


class Settings(BaseSettings):
    # ==========================================
    # 項目基礎
    # ==========================================
    PROJECT_NAME: str = "Matrix Intelligence"

    # ==========================================
    # 模型服務配置
    # ==========================================
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OPENAI_API_KEY: str = "ollama"

    # ==========================================
    # 核心模型選擇
    # ==========================================
    LLM_MODEL: str = "qwen2.5:1.5b"
    EMBEDDING_MODEL: str = "nomic-embed-text"

    # ==========================================
    # 🛡️ LLM 推理與安全參數
    # ==========================================
    LLM_TEMPERATURE: float = 0.1
    LLM_NUM_CTX: int = 4096
    LLM_TIMEOUT: int = 120

    # ==========================================
    # 📂 數據存儲路徑（自動計算絕對路徑）
    # ==========================================
    BASE_DIR: ClassVar[str] = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    DATA_DIR: ClassVar[str] = os.path.join(BASE_DIR, "data")

    VECTOR_DB_DIR: str = os.path.join(DATA_DIR, "vector_db")
    DATA_UPLOAD_DIR: str = os.path.join(DATA_DIR, "uploads")
    BM25_DB_DIR: str = os.path.join(DATA_DIR, "bm25_db")

    # ==========================================
    # 📝 文本處理參數（RAG 核心）
    # ==========================================
    CHUNK_SIZE: int = 400
    CHUNK_OVERLAP: int = 50

    # ==========================================
    # 📝 rerank 開關參數
    # ==========================================
    ENABLE_RERANK: bool = False  # CPU 無法跑動rerank，硬件升级后改为 True

    # ==========================================
    # 🎯 混合檢索與 RRF 調參
    # ==========================================
    TOP_K: int = 1
    RETRIEVAL_OVERSIZE_RATIO: int = 3
    RRF_K: int = 60
    VECTOR_DB_COLLECTION: str = "documents"

    # ==========================================
    # ⚡ 負載與併發控制
    # ==========================================
    BATCH_SIZE: int = 32
    INGEST_MAX_WORKERS: int = 4

    # ==========================================
    # 📋 日誌配置
    # ==========================================
    LOG_LEVEL: str = "INFO"

    # ==========================================
    # 🔧 特殊域配置（預留，未來 UI 可配置）
    # ==========================================
    SPECIAL_DOMAINS: List[str] = ["全域", "核心决策层", "未分类资产"]

    # ==========================================
    # Pydantic 配置
    # ==========================================
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    @field_validator("SPECIAL_DOMAINS", mode="before")
    @classmethod
    def parse_special_domains(cls, v):
        """解析 .env 中的逗號分隔字符串"""
        if isinstance(v, str):
            return [d.strip() for d in v.split(",") if d.strip()]
        return v

    def model_post_init(self, __context) -> None:
        """配置加載後校驗與初始化"""
        self._validate_chunk_params()
        self._ensure_directories()

    def _validate_chunk_params(self) -> None:
        """校驗分塊參數範圍"""
        if not (400 <= self.CHUNK_SIZE <= 1200):
            raise ValueError(f"CHUNK_SIZE 必須在 400-1200 範圍內，當前值: {self.CHUNK_SIZE}")
        if self.CHUNK_OVERLAP >= self.CHUNK_SIZE:
            raise ValueError(f"CHUNK_OVERLAP ({self.CHUNK_OVERLAP}) 必須小於 CHUNK_SIZE ({self.CHUNK_SIZE})")
        if self.CHUNK_OVERLAP < 0:
            raise ValueError(f"CHUNK_OVERLAP 不能為負數")

    def _ensure_directories(self) -> None:
        """確保必要目錄存在"""
        for dir_path in [self.DATA_DIR, self.VECTOR_DB_DIR, self.DATA_UPLOAD_DIR, self.BM25_DB_DIR]:
            os.makedirs(dir_path, exist_ok=True)


# ==========================================
# 全局單例
# ==========================================
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """獲取全局配置單例"""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


settings = get_settings()