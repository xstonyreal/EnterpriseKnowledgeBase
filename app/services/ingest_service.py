# app/services/ingest_service.py
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List

from app.config import settings
from app.core.logger import logger
from langchain_community.vectorstores import FAISS
from app.models.embeddings import embeddings
from langchain_core.documents import Document

# [架构级锁定]：全局单例变量
# 作用：根治 Streamlit 环境下因多次初始化导致的日志重复和内存浪费
_CACHED_VECTORSTORE = None

def _parallel_load_and_split() -> List[Document]:
    """
    【任务 B 核心】：并发解析引擎
    调用 pipeline 层的原子工具，利用多线程加速 50MB+ 文档的读取与切片。
    """
    # 局部导入，防止与 ingest_service 产生循环依赖
    from app.pipeline.ingest import list_all_files, process_file_to_docs

    files = list_all_files(settings.DATA_UPLOAD_DIR)
    all_docs = []

    if not files:
        logger.warning("📂 数据目录中未发现可处理的文件。")
        return all_docs

    # 引用全局配置：settings.INGEST_MAX_WORKERS
    logger.info(f"⚡ [并发引擎] 启动 {settings.INGEST_MAX_WORKERS} 线程并行解析...")

    with ThreadPoolExecutor(max_workers=settings.INGEST_MAX_WORKERS) as executor:
        # 任务分发
        future_to_file = {executor.submit(process_file_to_docs, f): f for f in files}

        for future in as_completed(future_to_file):
            file_name = future_to_file[future]
            try:
                docs = future.result()
                if docs:
                    all_docs.extend(docs)
            except Exception as e:
                logger.error(f"❌ [原子失效] 文件 {file_name} 解析崩溃: {e}")

    return all_docs


def initialize_knowledge_base(force_rebuild=False):
    """
    具备自省能力的初始化服务 (核心决策层)
    """
    global _CACHED_VECTORSTORE

    # 1. 【逻辑拦截】：如果实例已存在且非强制重构，直接返回缓存实例
    if _CACHED_VECTORSTORE is not None and not force_rebuild:
        return _CACHED_VECTORSTORE

    db_path = os.path.join(settings.CHROMA_PERSIST_DIR, "faiss_index")
    index_file = os.path.join(db_path, "index.faiss")

    # --- 流程 A: 资产热加载 ---
    if not force_rebuild and os.path.exists(index_file):
        logger.info("🔍 [手术刀] 执行高速热加载模式...")
        try:
            vectorstore = FAISS.load_local(
                db_path,
                embeddings,
                allow_dangerous_deserialization=True
            )
            logger.info("✅ [确定性] 既有知识索引已成功挂载。")
            _CACHED_VECTORSTORE = vectorstore
            return _CACHED_VECTORSTORE
        except Exception as e:
            logger.error(f"❌ [风险预警] 索引文件损坏，准备自动执行重构: {e}")

    # --- 流程 B: 知识重塑 (Task B 核心执行区) ---
    logger.info("🏗️ [核心工程] 正在执行全量知识重塑 (Ingest)...")
    start_time = time.time()

    try:
        # A. 并发获取 Document (取代旧的串行调用)
        documents: List[Document] = _parallel_load_and_split()

        if not documents:
            logger.warning("⚠️ [认知空间] 未能提取到有效文本。")
            return None

        # 引用全局配置：settings.INGEST_BATCH_SIZE
        logger.info(f"📊 [负载感知] 待处理切片: {len(documents)}，批次规模: {settings.INGEST_BATCH_SIZE}")

        vectorstore = None

        # B. 分批入库逻辑 (内存守护模式)
        for i in range(0, len(documents), settings.INGEST_BATCH_SIZE):
            batch = documents[i: i + settings.INGEST_BATCH_SIZE]

            if vectorstore is None:
                vectorstore = FAISS.from_documents(batch, embeddings)
            else:
                vectorstore.add_documents(batch)

            # 进度回显逻辑
            if (i // settings.INGEST_BATCH_SIZE) % 5 == 0:
                current_count = i + len(batch)
                progress = current_count / len(documents) * 100
                logger.info(f"🚀 [计算中] 向量化进度: {progress:.1f}% ({current_count}/{len(documents)})")

        # C. 结果物理固化 (确保存储目录存在并保存)
        if vectorstore:
            if not os.path.exists(db_path):
                os.makedirs(db_path)
            vectorstore.save_local(db_path)
            _CACHED_VECTORSTORE = vectorstore

            duration = time.time() - start_time
            logger.info(f"✅ [重塑成功] 耗时: {duration:.2f}s | 状态: 索引已物理锁定。")
            return _CACHED_VECTORSTORE

    except Exception as e:
        # --- 核心清理与回滚 ---
        _CACHED_VECTORSTORE = None
        error_info = str(e)
        logger.critical(f"🚨 [系统崩溃] 本地重构失败: {error_info}")

        # 针对性诊断建议
        if "10054" in error_info:
            logger.error("💡 [诊断] 连接重置，请确认 Ollama (Embedding 服务) 已启动。")
        elif "Memory" in error_info or "OOM" in error_info.upper():
            logger.error("💡 [诊断] 显存/内存溢出，请调小 Settings.INGEST_BATCH_SIZE。")

        raise e