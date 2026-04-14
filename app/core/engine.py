# app/core/engine.py
import os
from langchain_community.vectorstores import FAISS
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser

from app.models.llm import llm
from app.models.embeddings import embeddings
from app.config import settings
from app.core.logger import logger

def get_chat_response(query: str):
    """基于 LCEL 的 RAG 问答逻辑"""
    logger.info(f"🔍 正在检索知识库: {query}")

    db_path = os.path.join(settings.CHROMA_PERSIST_DIR, "faiss_index")
    if not os.path.exists(db_path):
        return "❌ 知识库尚未初始化，请先上传文件或运行入库脚本。"

    try:
        # 1. 加载库
        vector_db = FAISS.load_local(
            db_path,
            embeddings,
            allow_dangerous_deserialization=True
        )
        retriever = vector_db.as_retriever(search_kwargs={"k": settings.TOP_K})

        # 2. Prompt (适配 Qwen-0.5b)
        template = """你是一个专业的助手。请仅根据以下背景信息回答。
背景信息：
{context}

用户问题：{question}

如果背景中没有，请说不知道。直接给出回答，不要啰嗦。
回答："""
        prompt = ChatPromptTemplate.from_template(template)

        # 3. LCEL 链
        chain = (
            {"context": retriever, "question": RunnablePassthrough()}
            | prompt
            | llm
            | StrOutputParser()
        )

        # 4. 执行
        return chain.invoke(query)

    except Exception as e:
        logger.error(f"❌ 检索执行失败: {str(e)}")
        return f"❌ 系统繁忙，请稍后再试。错误: {str(e)}"