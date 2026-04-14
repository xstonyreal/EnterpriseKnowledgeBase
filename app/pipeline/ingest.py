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


def load_documents(directory: str):
    """遍历目录，加载所有支持的文件"""
    documents = []
    logger.info(f"📂 正在扫描目录: {directory}")

    if not os.path.exists(directory):
        logger.error(f"❌ 目录不存在: {directory}")
        return []

    for filename in os.listdir(directory):
        file_path = os.path.join(directory, filename)
        if os.path.isdir(file_path):
            continue

        try:
            if filename.lower().endswith(".pdf"):
                logger.info(f"📄 正在加载 PDF: {filename}")
                loader = PyPDFLoader(file_path)
                docs = loader.load()
            elif filename.lower().endswith(".txt"):
                logger.info(f"📝 正在加载 TXT: {filename}")
                try:
                    loader = TextLoader(file_path, encoding="utf-8")
                    docs = loader.load()
                except UnicodeDecodeError:
                    logger.warning(f"⚠️ UTF-8 失败，尝试 GBK: {filename}")
                    loader = TextLoader(file_path, encoding="gbk")
                    docs = loader.load()
            else:
                logger.info(f"📎 正在尝试加载其他文件: {filename}")
                loader = UnstructuredFileLoader(file_path)
                docs = loader.load()

            documents.extend(docs)
            logger.info(f"✅ 成功加载: {filename}")
        except Exception as e:
            logger.error(f"❌ 加载失败 [{filename}]: {str(e)}")
            continue

    return documents


def ingest_documents():
    """执行入库主流程"""
    logger.info("🚀 开始执行 FAISS 入库流程...")

    # 1. 加载文档
    docs = load_documents(settings.DATA_UPLOAD_DIR)
    if not docs:
        logger.error("❌ 未加载到任何文档，入库终止")
        return

    # 2. 文本切片
    logger.info(f"✂️ 正在切片，共 {len(docs)} 个文档...")
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.CHUNK_SIZE,
        chunk_overlap=settings.CHUNK_OVERLAP
    )
    splits = text_splitter.split_documents(docs)
    logger.info(f"✅ 切片完成，共 {len(splits)} 个片段")

    # 3. 生成向量并保存
    os.makedirs(settings.CHROMA_PERSIST_DIR, exist_ok=True)
    db_path = os.path.join(settings.CHROMA_PERSIST_DIR, "faiss_index")

    logger.info("🧠 正在生成向量索引 (调用 Ollama)...")
    vectorstore = FAISS.from_documents(documents=splits, embedding=embeddings)

    logger.info("✅ FAISS 索引生成完毕，准备保存...")
    vectorstore.save_local(db_path)
    logger.info(f"🎉 入库成功！索引已保存至: {db_path}")


if __name__ == "__main__":
    ingest_documents()