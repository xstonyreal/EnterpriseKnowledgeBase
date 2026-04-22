# app/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional, ClassVar  # 1. 在这里引入 ClassVar
import os  # 1. 引入 os 模块


class Settings(BaseSettings):
    # --- 项目基础 ---
    PROJECT_NAME: str = "Matrix Intelligence"

    # --- 模型服务配置 ---
    # Ollama 地址 (兼容 OpenAI 格式)
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    # Ollama 不需要 Key，但 LangChain 要求必须有
    OPENAI_API_KEY: str = "ollama"

    # --- 核心模型选择 ---
    LLM_MODEL: str = "qwen2.5:1.5b"
    EMBEDDING_MODEL: str = "nomic-embed-text"

    # ==========================================
    # 🛡️ 本地 LLM 性能与安全参数 (新增)
    # ==========================================
    # 1. 温度设置：0.1 确保保险业务回复的严谨性，防止幻觉
    LLM_TEMPERATURE: float = 0.1
    # 2. 上下文窗口：锁定为 4096，防止 1.5b 模型因 Context 过载导致 10054 错误
    LLM_NUM_CTX: int = 4096

    # --- 数据存储路径 ---
    # 1. 获取当前 config.py 文件所在的目录 (即 .../EnterpriseKnowledgeBase/app)
    BASE_DIR: ClassVar[str] = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    # 3. 拼接出 data 目录的绝对路径
    DATA_DIR: ClassVar[str] = os.path.join(BASE_DIR, "data")

    # --- 数据存储路径 ---
    # 4. 这里直接使用上面算好的绝对路径
    # 注意：这里仍然保留 : str 类型注解
    VECTOR_DB_DIR: str = os.path.join(DATA_DIR, "vector_db")
    DATA_UPLOAD_DIR: str = os.path.join(DATA_DIR, "uploads")

    # ==========================================
    # 📝 文本处理参数 (RAG 核心参数)
    # ==========================================
    # 分块大小：根据模型上下文窗口调整，1.5b 模型建议不要太大,下面参数修改后重新执行ingest.py
    CHUNK_SIZE: int = 400  #Gemini建议改小
    # 重叠部分：保持上下文连贯性
    CHUNK_OVERLAP: int = 80 # Gemini建议给多点提示信息
    # 检索返回数量
    TOP_K: int = 3

    # 向量库集合名称
    VECTOR_DB_COLLECTION: str = "documents"

    # --- Pydantic 设置 ---
    # env_file=".env" 告诉它去读根目录下的 .env 文件
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # ==========================================
    # ⚡ Matrix 负载与并发引擎配置 (核心注入)
    # ==========================================
    # --- [任务 B：负载与并发配置] ---
    # 批次大小：决定了 Embedding 过程中一次性送入显存的文本量。
    # 4G 显存建议 32-40，8G+ 显存可尝试 64-128。
    INGEST_BATCH_SIZE: int = 40
    # 并发线程数：决定了同时解析 PDF/Word 的数量。
    # 针对 I/O 密集型任务，建议设为 CPU 核心数的 1/2 或直接固定为 4。
    INGEST_MAX_WORKERS: int = 4


# 实例化配置，供其他模块直接导入使用
settings = Settings()