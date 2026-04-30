# models/embeddings.py
# 1. 修改导入：从 langchain_ollama 导入，而不是 langchain_openai
from langchain_ollama import OllamaEmbeddings
from app.config import settings
from app.core.logger import logger
from app.core.exceptions import dehydrate_exception


def get_embeddings():
    """初始化 Ollama Embedding 模型（單例）"""
    logger.info(f"🚀 初始化本地 Embedding 模型: {settings.EMBEDDING_MODEL}")

    # --- 修改点 1：路标 ---
    logger.debug("👉 准备实例化 OllamaEmbeddings 对象...")

    try:
        embeddings = OllamaEmbeddings(
            model=settings.EMBEDDING_MODEL,
            base_url=settings.OLLAMA_BASE_URL
        )
        logger.info("✅ Embedding 模型初始化成功")
        return embeddings
    except Exception as e:
        error_msg = f"Embedding 模型初始化失败: {settings.EMBEDDING_MODEL}"
        logger.error(error_msg)
        raise RuntimeError(error_msg) from e

# 全局单例
embeddings = get_embeddings()