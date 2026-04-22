# app/pipeline/ingest.py
import os
from datetime import datetime
from typing import List
from langchain_community.document_loaders import (
    TextLoader,
    PyPDFLoader,
    UnstructuredFileLoader,
)
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
from app.config import settings
from app.core.logger import logger

# --- 切片器实例化外移，减少重复开销 ---
_SPLITTER = RecursiveCharacterTextSplitter(
    chunk_size=settings.CHUNK_SIZE,
    chunk_overlap=settings.CHUNK_OVERLAP
)

def list_all_files(directory: str) -> List[str]:
    """
    【原子接口 1】：递归文件扫描器。
    职责：仅负责物理扫描，为多线程提供任务清单。
    """
    file_list = []

    if not os.path.exists(directory):
        logger.error(f"❌ 根目录不存在: {directory}")
        return []

    for root, dirs, files in os.walk(directory):
        for filename in files:
            # 过滤临时文件和隐藏文件
            if filename.startswith(('.', '~')):
                continue
            file_list.append(os.path.join(root, filename))

    return file_list


def process_file_to_docs(file_path: str) -> List[Document]:
    """
    【原子接口 2】：单文件并发处理器（Task B 核心）。
    职责：读取、Metadata 注入、物理切片。
    逻辑依据：保持线程安全，确保每一片 Document 都携带完整的业务标签。
    """
    filename = os.path.basename(file_path)
    base_directory = settings.DATA_UPLOAD_DIR

    # --- 优化点 1：时间戳一次性获取，供所有 chunk 复用 ---
    ingest_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 继承原有的业务域 (Domain) 计算逻辑
    rel_path = os.path.relpath(os.path.dirname(file_path), base_directory)
    domain = "未分类资产" if rel_path == "." else rel_path

    try:
        # 1. 动态选择加载器
        if filename.lower().endswith(".pdf"):
            loader = PyPDFLoader(file_path)

        elif filename.lower().endswith(".txt"):
            # --- [只改这里：增强初始化参数，不改变执行流] ---
            # 开启自动探测，如果失败则在加载阶段抛出异常，由下方的逻辑捕获
            loader = TextLoader(file_path, encoding="utf-8", autodetect_encoding=True)

        else:
            loader = UnstructuredFileLoader(file_path)

        # 2. 执行加载，这里引入了新的解码方式
        try:
            raw_docs = loader.load()
        except Exception as e:
            # 如果 utf-8/自动探测 彻底跪了，最后尝试一次 latin-1 暴力破解
            if filename.lower().endswith(".txt"):
                logger.warning(f"⚠️ [编码最终尝试] {filename} 切换至 latin-1")
                loader = TextLoader(file_path, encoding="latin-1")
                raw_docs = loader.load()
            else:
                raise e

        # 3. 注入 Metadata 契约
        for doc in raw_docs:
            doc.metadata["source"] = filename
            doc.metadata["domain"] = domain
            doc.metadata["ingest_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 4. 执行物理切片 (维持 context 连续性)
        splits = _SPLITTER.split_documents(raw_docs)
        logger.info(f"✅ [已标记 - {domain}] 加载成功: {filename} ({len(splits)} chunks)")
        return splits

    except Exception as e:
        logger.error(f"❌ 加载失败 [{filename}]: {str(e)}")
        return []


def load_and_split_all_documents() -> List[Document]:
    """
    【向后兼容接口】：
    内部通过原子函数串行实现，但在 ingest_service 中会被 _parallel_load_and_split 替代。
    """
    files = list_all_files(settings.DATA_UPLOAD_DIR)
    all_documents = []

    for file_path in files:
        all_documents.extend(process_file_to_docs(file_path))

    return all_documents

def ingest_documents():
    """
    【向后兼容接口】：
    为了不破坏原有的逻辑调用，保留此入口，但内部直接调用 Service 层。
    体现了“旧契约不变，新引擎升级”的工程平替思路。
    """
    from app.services.ingest_service import initialize_knowledge_base
    logger.info("🔄 [系统路由] 正在通过向后兼容接口触发全量重塑...")
    return initialize_knowledge_base(force_rebuild=True)