# app/core/vector_db.py
import os
from langchain_community.vectorstores import FAISS
from app.config import settings
from app.core.logger import logger
from app.models.embeddings import embeddings


def load_vector_db():
    """
    加载本地 FAISS 索引
    """
    db_path = os.path.join(settings.CHROMA_PERSIST_DIR, "faiss_index")

    if not os.path.exists(db_path):
        logger.warning(f"⚠️ 向量库不存在: {db_path}")
        return None

    logger.info(f"📚 正在加载向量库: {db_path}")
    try:
        vector_db = FAISS.load_local(db_path, embeddings, allow_dangerous_deserialization=True)
        logger.info("✅ 向量库加载成功")
        return vector_db
    except Exception as e:
        logger.error(f"❌ 向量库加载失败: {e}")
        return None


# 全局单例，避免重复加载
vector_db = load_vector_db()