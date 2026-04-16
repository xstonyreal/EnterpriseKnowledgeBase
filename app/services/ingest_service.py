# app/services/ingest_service.py
import os
from app.pipeline.ingest import ingest_documents
from app.config import settings
from app.core.logger import logger
from langchain_community.vectorstores import FAISS
from app.models.embeddings import embeddings


def initialize_knowledge_base(force_rebuild=False):
    """
    具备自省能力的初始化服务：
    - force_rebuild=False (默认): 检测到索引存在即加载，实现“秒开”。
    - force_rebuild=True: 强制清空并重新执行全量切片。
    """
    db_path = os.path.join(settings.CHROMA_PERSIST_DIR, "faiss_index")
    index_file = os.path.join(db_path, "index.faiss")

    # 1. 判断是否需要跳过重构
    if not force_rebuild and os.path.exists(index_file):
        logger.info("🔍 监测到现有向量资产，执行高速热加载模式...")
        try:
            vectorstore = FAISS.load_local(
                db_path,
                embeddings,
                allow_dangerous_deserialization=True
            )
            logger.info("✅ 既有知识索引已成功挂载至内存。")
            return vectorstore
        except Exception as e:
            logger.error(f"❌ 索引加载失败，准备自动修复 (重新入库): {e}")

    # 2. 否则执行全量入库逻辑
    logger.info("🏗️ 正在执行全量知识重塑 (Ingest)...")
    ingest_documents()

    # 3. 入库完成后加载新生成的索引
    return FAISS.load_local(
        db_path,
        embeddings,
        allow_dangerous_deserialization=True
    )