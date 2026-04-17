# app/pipeline/ingest.py
import os
from langchain_community.document_loaders import (
    TextLoader,
    PyPDFLoader,
    UnstructuredFileLoader,
)
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from app.models.embeddings import embeddings
from app.config import settings
from app.core.logger import logger
from datetime import datetime


def load_documents_recursive(base_directory: str):
    """
    【手术刀重构】：深度递归扫描
    不仅加载文件，还负责捕捉文件夹名称作为业务域（Domain）标签。
    """
    all_documents = []
    logger.info(f"📂 启动深度扫描模式: {base_directory}")

    if not os.path.exists(base_directory):
        logger.error(f"❌ 根目录不存在: {base_directory}")
        return []

    # 使用 os.walk 进行全量遍历
    for root, dirs, files in os.walk(base_directory):
        # 1. 计算当前文件夹相对于根目录的名称，作为业务域标签
        rel_path = os.path.relpath(root, base_directory)
        domain = "未分类资产" if rel_path == "." else rel_path

        for filename in files:
            if filename.startswith(('.', '~')): continue  # 忽略临时文件

            file_path = os.path.join(root, filename)
            try:
                # 2. 根据后缀选择加载器
                if filename.lower().endswith(".pdf"):
                    loader = PyPDFLoader(file_path)
                    docs = loader.load()
                elif filename.lower().endswith(".txt"):
                    try:
                        loader = TextLoader(file_path, encoding="utf-8")
                        docs = loader.load()
                    except UnicodeDecodeError:
                        loader = TextLoader(file_path, encoding="gbk")
                        docs = loader.load()
                else:
                    loader = UnstructuredFileLoader(file_path)
                    docs = loader.load()

                # --- [Metadata 手术刀注入] ---
                # 在这里，我们将每一个文档分片强行打上业务印记
                for doc in docs:
                    doc.metadata["source"] = filename
                    doc.metadata["domain"] = domain  # 核心：业务域标记
                    doc.metadata["ingest_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                all_documents.extend(docs)
                logger.info(f"✅ [已标记 - {domain}] 加载成功: {filename}")

            except Exception as e:
                logger.error(f"❌ 加载失败 [{filename}]: {str(e)}")
                continue

    return all_documents


def ingest_documents():
    """执行入库主流程：从脱水到切片再到逻辑注入"""
    logger.info("🚀 [核心工程] 开始执行 FAISS 索引重塑...")

    # 1. 递归加载并打标
    docs = load_documents_recursive(settings.DATA_UPLOAD_DIR)
    if not docs:
        logger.error("❌ 未发现可集成资产，入库终止")
        return

    # 2. 物理切片 (维持 context 连续性)
    logger.info(f"✂️ 正在执行逻辑分片，资产基数: {len(docs)} docs...")
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.CHUNK_SIZE,
        chunk_overlap=settings.CHUNK_OVERLAP
    )

    # split_documents 会自动保留原 doc 的 metadata
    splits = text_splitter.split_documents(docs)
    logger.info(f"✅ 分片完成，逻辑单元总数: {len(splits)}")

    # 3. 向量空间持久化
    os.makedirs(settings.CHROMA_PERSIST_DIR, exist_ok=True)
    db_path = os.path.join(settings.CHROMA_PERSIST_DIR, "faiss_index")

    logger.info("🧠 正在生成向量表征 (嵌入模型同步中)...")
    vectorstore = FAISS.from_documents(documents=splits, embedding=embeddings)

    logger.info("💾 正在将索引固化至物理磁盘...")
    vectorstore.save_local(db_path)
    logger.info(f"🎉 [工程完毕] 认知资产已安全注入。路径: {db_path}")


if __name__ == "__main__":
    ingest_documents()