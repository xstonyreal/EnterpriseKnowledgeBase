# app/pipeline/ingest.py

from datetime import datetime
from typing import List
from pathlib import Path
from langchain_community.document_loaders import (
    TextLoader,
    PyPDFLoader,
    UnstructuredFileLoader,
)
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
from app.config import settings
from app.core.logger import logger

# 增加office 文檔處理能力，放在函數内加載
# import pandas as pd
# from docx import Document as DocxDocument
# from pptx import Presentation

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
    root_path = Path(directory)

    if not root_path.exists():
        logger.error(f"❌ 根目錄不存在: {directory}")
        return []

    for file in root_path.rglob('*'):
        if file.is_file() and not file.name.startswith(('.', '~')):
            file_list.append(str(file.absolute()))
    return file_list


def process_file_to_docs(file_path: str) -> List[Document]:
    """
    【原子接口 2】：單文件解析引擎：負責編碼探測、格式適配與元數據歸一化
    """
    p = Path(file_path)
    base_p = Path(settings.DATA_UPLOAD_DIR)
    ingest_time = datetime.now().isoformat()

    # 【關鍵：歸一化路徑】轉為 Posix 風格 (正斜槓) 作為數據庫唯一標籤
    rel_path = p.relative_to(base_p)
    normalized_source = rel_path.as_posix()

    # 【關鍵：物理域隔離】取第一級目錄名作為 Domain
    domain = rel_path.parts[0] if len(rel_path.parts) > 1 else "未分類資產"

    try:
        raw_docs = []
        ext = p.suffix.lower()

        if ext == ".pdf":
            loader = PyPDFLoader(str(p))
            raw_docs = loader.load()
        elif ext == ".txt":
            # 中文優先編碼探測鏈
            success = False
            for enc in ["utf-8", "gbk", "gb18030", "big5"]:
                try:
                    loader = TextLoader(str(p), encoding=enc)
                    raw_docs = loader.load()
                    success = True
                    break
                except (UnicodeDecodeError, LookupError):
                    continue
            if not success: raise ValueError("無法識別文本編碼")
        elif ext == ".docx":
            from docx import Document as DocxDocument
            doc_obj = DocxDocument(str(p))
            content = "\n".join([para.text for para in doc_obj.paragraphs])
            raw_docs = [Document(page_content=content)]
        elif ext in [".pptx", ".ppt"]:
            from pptx import Presentation
            prs = Presentation(p)
            text_elements = []
            for slide in prs.slides:
                for shape in slide.shapes:
                    if hasattr(shape, "text"): text_elements.append(shape.text)
            raw_docs = [Document(page_content="\n".join(text_elements))]
        else:
            loader = UnstructuredFileLoader(str(p))
            raw_docs = loader.load()

        # 注入元數據契約
        for doc in raw_docs:
            doc.metadata.update({
                "source": normalized_source,
                "domain": domain,
                "ingest_time": ingest_time
            })

        splits = _SPLITTER.split_documents(raw_docs)
        logger.info(f"✅ [解析成功] {normalized_source} -> {len(splits)} chunks")
        return splits

    except Exception as e:
        logger.error(f"❌ 解析失敗 [{p.name}]: {str(e)}")
        return []