# app/api/chat.py
import os
from langchain_community.vectorstores import FAISS
# 👇 修改点：直接从 config 导入 LLM 对象
from app.config import settings, LLM
from app.models.embeddings import embeddings
from app.core.logger import logger
from langchain_core.output_parsers import StrOutputParser

# 1. 初始化全局变量，避免重复加载
vectorstore = None
qa_chain = None


def get_qa_chain():
    try:
        # 1. 加载 FAISS 索引
        logger.info("🔍 正在加载本地 FAISS 索引...")
        db_path = os.path.join(settings.CHROMA_PERSIST_DIR, "faiss_index")

        if not os.path.exists(db_path):
            logger.error(f"❌ 索引目录不存在: {db_path}")
            logger.error("💡 请先运行 ingest.py 进行入库！")
            return None

        vectorstore = FAISS.load_local(db_path, embeddings, allow_dangerous_deserialization=True)
        logger.info("✅ FAISS 索引加载成功！")

        # 2. 创建检索器
        retriever = vectorstore.as_retriever(
            search_kwargs={"k": settings.TOP_K},
            query_constructor=lambda x: x["question"]
        )

        # 3. 创建提示词
        from langchain_core.prompts import ChatPromptTemplate

        template = """基于以下已知信息，简洁和专业地回答用户的问题。如果无法从中得到答案，请说“根据已知信息无法回答该问题”。

        已知信息：
        {context}

        用户问题：{question}

        回答："""

        prompt = ChatPromptTemplate.from_template(template)

        # 4. 构建 LCEL 链 (完全不用 langchain.chains)
        from langchain_core.output_parsers import StrOutputParser

        # 这是最纯粹的 LCEL 写法，不依赖任何 chains 模块
        qa_chain = (
                {"context": retriever, "question": lambda x: x["question"]}
                | prompt
                | LLM
                | StrOutputParser()
        )

        logger.info("✅ 问答引擎初始化完毕！")
        return qa_chain

    except Exception as e:
        logger.error(f"❌ 加载索引失败: {str(e)}")
        return None


def ask_question(query: str):
    """
    核心问答函数
    """
    logger.info(f"👤 用户提问: {query}")

    # 获取问答链
    chain = get_qa_chain()
    if not chain:
        return "❌ 系统未初始化，请先检查日志。"

    try:
        # 5. 执行调用
        result = chain.invoke({"question": query})

        # 提取答案
        answer = result.get("answer", "无回答内容")

        # 提取来源（可选，用于展示参考文档）
        source_docs = result.get("context", [])
        sources = [doc.page_content[:50] + "..." for doc in source_docs]  # 只取前50个字预览

        logger.success("✅ 回答生成完毕")

        return {
            "answer": answer,
            "sources": sources
        }

    except Exception as e:
        logger.error(f"❌ 问答过程出错: {str(e)}")
        return f"出错了: {str(e)}"


# --- 本地测试代码 ---
if __name__ == "__main__":
    print("🤖 知识库问答助手已就绪 (输入 'exit' 退出)")
    while True:
        query = input("\n请输入问题: ")
        if query.lower() in ["exit", "quit", "退出"]:
            break
        response = ask_question(query)
        if isinstance(response, dict):
            print(f"\n🤖 AI: {response['answer']}")
            print(f"📚 参考: {response['sources']}")
        else:
            print(f"\n❌ {response}")