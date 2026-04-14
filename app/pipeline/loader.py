# app/pipeline/loader.py
import os
from typing import List
from app.core.logger import logger

# 尝试导入非必须库，防止报错
try:
    import PyPDF2
    import docx

    PDF_SUPPORT = True
except ImportError:
    PDF_SUPPORT = False
    logger.warning("⚠️ 未安装 PDF/Word 库，仅支持 TXT 格式。请运行: pip install pypdf2 python-docx")


def load_document(file_path: str) -> str:
    """
    读取单个文件，返回纯文本内容
    支持 .txt, .pdf, .docx
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"文件不存在: {file_path}")

    _, ext = os.path.splitext(file_path)
    ext = ext.lower()

    logger.info(f"📄 正在加载文件: {file_path}")

    content = ""

    # 1. 处理 TXT
    if ext == '.txt':
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

    # 2. 处理 PDF
    elif ext == '.pdf':
        if not PDF_SUPPORT:
            raise ImportError("需要安装 pypdf2 库")
        with open(file_path, 'rb') as f:
            reader = PyPDF2.PdfReader(f)
            for page in reader.pages:
                content += page.extract_text() + "\n"

    # 3. 处理 Word
    elif ext == '.docx':
        if not PDF_SUPPORT:
            raise ImportError("需要安装 python-docx 库")
        doc = docx.Document(file_path)
        for para in doc.paragraphs:
            content += para.text + "\n"

    else:
        logger.warning(f"⚠️ 不支持的文件格式: {ext}，尝试以文本读取")
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

    return content.strip()


def load_directory(directory_path: str) -> List[dict]:
    """
    批量读取目录下所有支持的文件
    返回: [{'filename': 'xxx', 'content': '...'}, ...]
    """
    docs = []
    logger.info(f"📂 扫描目录: {directory_path}")

    for filename in os.listdir(directory_path):
        file_path = os.path.join(directory_path, filename)
        if os.path.isfile(file_path):
            try:
                content = load_document(file_path)
                if content:
                    docs.append({'filename': filename, 'content': content})
            except Exception as e:
                logger.error(f"❌ 读取失败 {filename}: {e}")

    return docs