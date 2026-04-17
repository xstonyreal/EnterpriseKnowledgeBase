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


def get_vector_db():
    """确保单例获取向量库，防止重复加载"""
    global vector_db
    if vector_db is None:
        if os.path.exists(db_path):
            logger.info(f"💾 加载本地索引: {db_path}")
            # 注意：这里的 embeddings 必须与入库时一致
            vector_db = FAISS.load_local(db_path, embeddings, allow_dangerous_deserialization=True)
        else:
            logger.error("❌ 找不到索引文件，请先运行数据入库脚本。")
    return vector_db


def format_docs_with_source(docs):
    parts = []
    for i, doc in enumerate(docs):
        # 增加 domain 显示，方便调试和展示
        source = doc.metadata.get("source", "未知来源")
        domain = doc.metadata.get("domain", "通用")
        content = doc.page_content.replace('\n', ' ')
        parts.append(f"--- 资料项 {i + 1} [领域: {domain} | 来源: {source}] ---\n{content}")
    return "\n\n".join(parts)


# --- [主引擎：手术刀精度版] ---
def get_chat_response_stream(query: str, filter_domain: str = None):
    """
    重构后的流式引擎：
    :param query: 用户输入
    :param filter_domain: UI 侧边栏选中的业务域
    """
    db = get_vector_db()
    if db is None:
        def err_gen(): yield "❌ 引擎未就绪，请检查索引文件。"

        return err_gen(), []

    query_l = query.lower().strip()

    # 1. 🛡️ 极简拦截（保持原有逻辑）
    pure_greetings = ["hello", "hi", "你好", "哈喽", "在吗", "嗨", "早上好", "下午好"]
    if query_l in pure_greetings:
        def greeting_gen():
            yield f"您好！我是您的智慧助手。当前已锁定业务域：`{filter_domain or '全域'}`。请键入您的指令。"

        return greeting_gen(), []

    try:
        # 2. 🔍 精准检索：引入 Metadata Filter
        # 逻辑：如果选了特定部门且不是“核心决策层”，则强行开启物理隔离检索
        search_kwargs = {"k": settings.TOP_K}

        # 【关键手术位】：注入过滤参数
        if filter_domain and filter_domain != "核心决策层" and filter_domain != "未分类资产":
            # FAISS 的 filter 参数要求 metadata 字典匹配
            search_kwargs["filter"] = {"domain": filter_domain}
            logger.info(f"🎯 [精准模式] 检索范围已锁定至: {filter_domain}")
        else:
            logger.info("网开一面 [全域模式] 正在跨部门检索...")

        docs = db.similarity_search(query, **search_kwargs)

        # 3. 🛑 零知识拦截：如果选了域但搜不到东西
        if not docs and filter_domain and filter_domain != "核心决策层":
            def empty_gen():
                yield f"⚠️ 在当前业务域 **[{filter_domain}]** 中未检索到相关资产。为了保证回答的确定性，我已拦截了通用幻觉输出。请检查资产是否已同步至该目录。"

            return empty_gen(), []

        sources = list(set([doc.metadata.get("source", "未知来源") for doc in docs]))
        context_text = format_docs_with_source(docs)

        # 4. 🧠 Prompt 维持原有人设
        template = """你是一个专业的保险业务智慧助手。
当前检索域：{domain_info}

【回答优先级指南】
1. **优先库内匹配**：如果[背景信息]中有直接相关的条款，请严谨回答。
2. **拒绝跨域猜测**：如果背景信息中没有答案，请诚实告知。
3. **专业人设**：维持保险助手的逻辑性。

[背景信息]:
{context}

[用户问题]:
{question}

回答："""

        prompt_text = ChatPromptTemplate.from_template(template)
        chain = prompt_text | llm | StrOutputParser()

        def stream_generator():
            # 这里的 domain_info 只是为了让 LLM 知道它现在被关在哪
            domain_info = filter_domain if filter_domain else "全域开放"
            for chunk in chain.stream({"context": context_text, "question": query, "domain_info": domain_info}):
                yield chunk

        return stream_generator(), sources

    except Exception as e:
        logger.error(f"❌ 执行异常: {str(e)}")

        def err_gen():
            yield f"❌ 抱歉，逻辑链路出现震荡: {str(e)}"

        return err_gen(), []