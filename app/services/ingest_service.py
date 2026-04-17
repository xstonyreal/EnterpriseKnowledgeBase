# app/services/ingest_service.py
import os
from app.pipeline.ingest import ingest_documents
from app.config import settings
from app.core.logger import logger
from langchain_community.vectorstores import FAISS
from app.models.embeddings import embeddings

# [架构级锁定]：全局单例变量。
# 作用：即使 Streamlit 多次调用初始化，只要内存中已有实例，就拒绝二次执行，彻底根治日志重复。
_CACHED_VECTORSTORE = None


def initialize_knowledge_base(force_rebuild=False):
    """
    具备自省能力的初始化服务 (核心决策层)：
    - force_rebuild=False (默认): 优先热加载，实现秒级启动，节省 Embedding 算力。
    - force_rebuild=True: 强制物理重构。当 Metadata 标签污染或数据过期时手动触发。
    """
    global _CACHED_VECTORSTORE

    # 【逻辑拦截】：如果实例已存在且非强制重构，保持静默，直接返回。
    if _CACHED_VECTORSTORE is not None and not force_rebuild:
        return _CACHED_VECTORSTORE

    db_path = os.path.join(settings.CHROMA_PERSIST_DIR, "faiss_index")
    index_file = os.path.join(db_path, "index.faiss")

    # --- 流程 A: 资产热加载 ---
    if not force_rebuild and os.path.exists(index_file):
        logger.info("🔍 [手术刀] 监测到现有向量资产，执行高速热加载模式...")
        try:
            # 允许危险反序列化是为了在本地环境中快速读取 FAISS 二进制索引
            vectorstore = FAISS.load_local(
                db_path,
                embeddings,
                allow_dangerous_deserialization=True
            )
            logger.info("✅ [确定性] 既有知识索引已成功挂载至内存。")
            _CACHED_VECTORSTORE = vectorstore
            return _CACHED_VECTORSTORE
        except Exception as e:
            logger.error(f"❌ [风险预警] 索引文件损坏或读取异常，准备自动执行修复程序: {e}")

    # --- 流程 B: 知识重塑 (GIGO 拦截点) ---
    # 场景：初次运行或用户点击了“强制重构”按钮
    logger.info("🏗️ [核心工程] 正在执行全量知识重塑 (Ingest)...")

    # 此处调用底层 Pipeline，它会扫描 uploads 目录并根据文件夹名称打上 Metadata 标签
    ingest_documents()

    # 重构完成后，将新索引载入内存
    _CACHED_VECTORSTORE = FAISS.load_local(
        db_path,
        embeddings,
        allow_dangerous_deserialization=True
    )
    logger.info("✅ [认知空间] 全量审计完成，新索引已生效并锁定。")
    return _CACHED_VECTORSTORE