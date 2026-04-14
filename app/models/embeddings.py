# models/embeddings.py
# 1. 修改导入：从 langchain_ollama 导入，而不是 langchain_openai
from langchain_ollama import OllamaEmbeddings
from app.config import settings
from app.core.logger import logger
# 如果不再需要 settings 中的 OpenAI 配置，可以保留导入但不再使用相关字段

def get_embeddings():
    logger.info(f"🚀 初始化本地 Embedding 模型: {settings.EMBEDDING_MODEL}")

    # --- 修改点 1：路标 ---
    print("👉 准备实例化 OllamaEmbeddings 对象...")

    # 2. 修改实例化：使用 OllamaEmbeddings
    embeddings = OllamaEmbeddings(
        model=settings.EMBEDDING_MODEL,       # 同.env settings
        base_url=settings.OLLAMA_BASE_URL # 同.env settings
        # 注意：本地 Ollama 不需要 api_key，也不需要 openai_api_base
    )

    # --- 修改点 2：路标 ---
    print("✅ OllamaEmbeddings 对象实例化成功！")

    return embeddings

# 全局单例
embeddings = get_embeddings()