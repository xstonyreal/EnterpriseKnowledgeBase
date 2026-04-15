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


# ==========================================================
# 🚀 优化点：单例加载
# 在模块加载时就完成 FAISS 初始化，避免每次提问都读硬盘
# ==========================================================

db_path = os.path.join(settings.CHROMA_PERSIST_DIR, "faiss_index")

if os.path.exists(db_path):
    logger.info(f"💾 正在将向量库载入内存: {db_path}")
    # 这一步在 16GB 内存上只跑一次，之后提问就“秒开”了
    vector_db = FAISS.load_local(
        db_path,
        embeddings,
        allow_dangerous_deserialization=True
    )
else:
    logger.warning("⚠️ 向量库路径不存在，请先执行入库脚本！")
    vector_db = None

def get_chat_response(query: str):
    """基于 LCEL 的 RAG 问答逻辑"""
    # ✨ 核心修复：声明使用外部的全局变量
    global vector_db

    if vector_db is None:
        return "❌ 知识库尚未初始化，请先上传文件或运行入库脚本。"
    logger.info(f"🔍 正在检索知识库: {query}")


    try:
        # 1. 加载库
        vector_db = FAISS.load_local(
            db_path,
            embeddings,
            allow_dangerous_deserialization=True
        )
        retriever = vector_db.as_retriever(search_kwargs={"k": settings.TOP_K})

        # 2. Prompt (适配 Qwen-1.5b)
        #由于引入qwen 1.5b，已经具备一定的智力，提示词进行优化
        template = """你是一个专业的外部顾问和企业助手。请结合背景信息和你的知识回答。
1.如果背景信息中没有相关内容，请结合你自身的知识储备给出准确回答。
2.只有当你完全不确定且背景也未提及时，才说不知道。
3.直接给出回答，不要啰嗦
背景信息：
{context}

用户问题：{question}
。
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