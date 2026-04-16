# app/core/engine.py
import os
from langchain_community.vectorstores import FAISS
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from app.models.llm import llm
from app.models.embeddings import embeddings
from app.config import settings
from app.core.logger import logger

# --- [单例加载向量库] ---
db_path = os.path.join(settings.CHROMA_PERSIST_DIR, "faiss_index")
vector_db = None

if os.path.exists(db_path):
    logger.info(f"💾 加载本地索引: {db_path}")
    vector_db = FAISS.load_local(db_path, embeddings, allow_dangerous_deserialization=True)
else:
    logger.error("❌ 找不到索引文件，请先运行数据入库脚本。")


def format_docs_with_source(docs):
    parts = []
    for i, doc in enumerate(docs):
        source = doc.metadata.get("source", "未知来源")
        content = doc.page_content.replace('\n', ' ')
        parts.append(f"--- 资料项 {i + 1} [来源: {source}] ---\n{content}")
    return "\n\n".join(parts)


# --- [主引擎：智商与稳健平衡版] ---
def get_chat_response_stream(query: str):
    if vector_db is None:
        def err_gen(): yield "❌ 引擎未就绪。"

        return err_gen(), []

    query_l = query.lower().strip()

    # 1. 🛡️ 极简拦截：只处理纯粹的打招呼，给用户一个“我在营业”的反馈
    pure_greetings = ["hello", "hi", "你好", "哈喽", "在吗", "嗨", "早上好", "下午好"]
    if query_l in pure_greetings:
        def greeting_gen():
            yield f"您好！我是您的保险智慧助手。您可以向我咨询《{settings.PROJECT_NAME}》的业务细则，或者探讨通用的保险与风险话题。"

        return greeting_gen(), []

    try:
        # 2. 🔍 检索业务背景
        docs = vector_db.similarity_search(query, k=settings.TOP_K)
        sources = list(set([doc.metadata.get("source", "未知来源") for doc in docs]))
        context_text = format_docs_with_source(docs)

        # 3. 🧠 【核心改变点】Prompt 逻辑微调
        # 这里取消了那种“没找到就报错”的死命令，改为“优先库内，兼顾通用”
        template = """你是一个专业的保险业务智慧助手。

【回答优先级指南】
1. **优先库内匹配**：如果[背景信息]中有与[用户问题]直接相关的条款或标准，请务必基于背景信息回答，并保持严谨。
2. **泛业务引导**：如果[背景信息]没有直接答案（如问：登月保险、通用航空险、AI如何改变保险），只要问题涉及保险、风险、金融或逻辑探讨，请结合你的通用常识给出专业的引导性建议，不要简单回答“未找到”。
3. **保持身份**：即便在进行通用对话，也要维持“保险业务助手”的专业人设。
4. **拒绝极端无关**：只有当问题完全是胡言乱语、政治敏感或娱乐八卦时，才礼貌拒绝。

[背景信息]:
{context}

[用户问题]:
{question}

回答："""

        prompt = ChatPromptTemplate.from_template(template)
        chain = prompt | llm | StrOutputParser()

        def stream_generator():
            for chunk in chain.stream({"context": context_text, "question": query}):
                yield chunk

        return stream_generator(), sources

    except Exception as e:
        logger.error(f"❌ 执行异常: {str(e)}")

        def err_gen():
            yield f"❌ 抱歉，我出了一点小差错: {str(e)}"

        return err_gen(), []