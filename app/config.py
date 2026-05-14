import os
from typing import ClassVar, List, Any
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator
from pathlib import Path
from dotenv import load_dotenv

# ============================
# 全局线程安全配置（工业级标准）
# ============================
os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"

# 强制加载环境变量
load_dotenv()

class Settings(BaseSettings):
    # ==========================================
    # 项目基础
    # ==========================================
    PROJECT_NAME: str = "Matrix Intelligence"

    # ==========================================
    # 服务配置
    # ==========================================
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OPENAI_API_KEY: str = "ollama"

    # ==========================================
    # 模型配置
    # ==========================================
    LLM_MODEL: str = "qwen2.5:1.5b"
    EMBEDDING_MODEL: str = "nomic-embed-text"
    RERANK_MODEL_NAME: str = "BAAI/bge-reranker-base"

    # ==========================================
    # RAG 核心参数
    # ==========================================
    ENABLE_RERANK: bool = False
    CHUNK_SIZE: int = 400
    CHUNK_OVERLAP: int = 50
    TOP_K: int = 5
    RETRIEVAL_OVERSIZE_RATIO: int = 3
    RRF_K: int = 60
    HYBRID_SEARCH_WEIGHTS: List[float] = [0.6, 0.4]

    # ==========================================
    # LLM 参数
    # ==========================================
    LLM_TEMPERATURE: float = 0.1
    LLM_NUM_CTX: int = 4096
    LLM_TIMEOUT: int = 120

    # ==========================================
    # 并发 & 日志
    # ==========================================
    BATCH_SIZE: int = 32
    INGEST_MAX_WORKERS: int = 4
    LOG_LEVEL: str = "INFO"

    # ==========================================
    # 固定结构 & 路径（不进 env）
    # ==========================================
    BASE_DIR: ClassVar[Path] = Path(__file__).resolve().parent.parent
    DATA_DIR: ClassVar[Path] = BASE_DIR / "data"

    VECTOR_DB_DIR: Path = DATA_DIR / "vector_db"
    DATA_UPLOAD_DIR: Path = DATA_DIR / "uploads"
    BM25_DB_DIR: Path = DATA_DIR / "bm25_db"
    MANIFEST_FILE: Path = DATA_DIR / "vector_db" / "manifest.json"
    RERANK_MODEL_PATH: Path = BASE_DIR / "models" / "bge_reranker_base"

    SPECIAL_DOMAINS: List[str] = ["全域", "核心决策层", "未分类资产"]

    # ==========================================
    # Pydantic 配置
    # ==========================================
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # ==========================================
    # 强力清洗过滤器（全部保留）
    # ==========================================
    @field_validator("ENABLE_RERANK", mode="before")
    @classmethod
    def clean_bool(cls, v: Any) -> bool:
        if isinstance(v, str):
            clean_v = v.split('#')[0].strip().lower()
            return clean_v == 'true'
        return bool(v)

    @field_validator("LLM_NUM_CTX", "LLM_TIMEOUT", "CHUNK_SIZE", "CHUNK_OVERLAP", "TOP_K", mode="before")
    @classmethod
    def clean_int(cls, v: Any) -> int:
        if isinstance(v, str):
            clean_v = v.split('#')[0].strip()
            return int("".join(filter(str.isdigit, clean_v)) or 0)
        return int(v)

    @field_validator("LLM_TEMPERATURE", mode="before")
    @classmethod
    def clean_float(cls, v: Any) -> float:
        if isinstance(v, str):
            clean_v = v.split('#')[0].strip()
            return float(clean_v)
        return float(v)

    @field_validator("SPECIAL_DOMAINS", mode="before")
    @classmethod
    def parse_domains(cls, v: Any) -> List[str]:
        if isinstance(v, str):
            clean_v = v.split('#')[0].strip()
            return [d.strip() for d in clean_v.split(",") if d.strip()]
        return v

    @field_validator("HYBRID_SEARCH_WEIGHTS", mode="before")
    @classmethod
    def parse_weights(cls, v: Any) -> List[float]:
        if isinstance(v, str):
            clean_v = v.split('#')[0].strip()
            return [float(i) for i in clean_v.split(",") if i.strip()]
        return v

    # ==========================================
    # 初始化钩子
    # ==========================================
    def model_post_init(self, __context) -> None:
        self._ensure_directories()
        self._ensure_nltk_data()
        self._validate_logic()

    def _validate_logic(self) -> None:
        if self.CHUNK_OVERLAP >= self.CHUNK_SIZE:
            raise ValueError("CHUNK_OVERLAP 必須小於 CHUNK_SIZE")

    def _ensure_directories(self) -> None:
        for dir_path in [self.DATA_DIR, self.VECTOR_DB_DIR, self.DATA_UPLOAD_DIR, self.BM25_DB_DIR]:
            dir_path.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _ensure_nltk_data() -> None:
        import nltk
        try:
            nltk.data.find('tokenizers/punkt_tab')
        except (LookupError, Exception):
            print("📡 [Config] 正在初始化 NLTK 數據...")
            try:
                nltk.download('punkt', quiet=True)
                nltk.download('punkt_tab', quiet=True)
            except Exception:
                pass

# ============================
# 单例导出
# ============================
settings = Settings()