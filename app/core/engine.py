# app/core/engine.py

import os
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

# 统一从 models 引入，保持单例
from app.models.llm import llm
# 注意：embeddings 在 initialize_knowledge_base 内部已处理，此处仅在 format 时可能用到
from app.config import settings
from app.core.logger import logger
# 【契约对齐】：必须统一使用 service 层定义的单例加载器
from app.services.ingest_service import initialize_knowledge_base


def format_docs_with_source(docs):
    """格式化检索到的文档，保留 Matrix 分域标签"""
    parts = []
    for i, doc in enumerate(docs):
        source = doc.metadata.get("source", "未知来源")
        domain = doc.metadata.get("domain", "通用")
        # 移除换行符，防止破坏 Prompt 结构
        content = doc.page_content.replace('\n', ' ')
        parts.append(f"--- 资料项 {i + 1} [领域: {domain} | 来源: {source}] ---\n{content}")
    return "\n\n".join(parts)


def get_chat_response(query: str, filter_domain: str = None) -> str:
    """
    【同步兼容层】：专为 main.py (CLI) 提供服务。
    内部封装流式生成器并聚合结果。
    """
    stream_gen, sources = get_chat_response_stream(query, filter_domain)
    full_response = "".join(list(stream_gen))
    return full_response


def get_chat_response_stream(query: str, filter_domain: str = None):
    """
    Matrix Intelligence 重构版流式引擎：
    :param query: 用户输入
    :param filter_domain: UI 或逻辑层选中的业务域
    """
    # 【核心手术位】：弃用本地 get_vector_db，改用底座统一初始化服务
    db = initialize_knowledge_base()

    if db is None:
        def err_gen(): yield "❌ Matrix 底座未就绪，请检查 data/uploads 是否有资产并执行同步。"

        return err_gen(), []

    query_l = query.lower().strip()

    # 1. 🛡️ 极简拦截：保持原有逻辑
    pure_greetings = ["hello", "hi", "你好", "哈喽", "在吗", "嗨", "早上好", "下午好"]
    if query_l in pure_greetings:
        def greeting_gen():
            yield f"您好！我是您的智慧助手。当前已锁定业务域：`{filter_domain or '全域'}`。请键入您的业务指令。"

        return greeting_gen(), []

    try:
        # 2. 🔍 精准检索：Matrix 分域隔离过滤
        # 使用 settings.TOP_K 替代硬编码
        search_kwargs = {"k": settings.TOP_K}

        # 注入过滤参数：FAISS 物理隔离检索
        if filter_domain and filter_domain not in ["核心决策层", "未分类资产", "全域"]:
            search_kwargs["filter"] = {"domain": filter_domain}
            logger.info(f"🎯 [Matrix 精准模式] 检索范围锁定: {filter_domain}")
        else:
            logger.info("🌐 [Matrix 全域模式] 执行跨域语义检索...")

        docs = db.similarity_search(query, **search_kwargs)

        # 3. 🛑 零知识拦截
        if not docs and filter_domain and filter_domain not in ["核心决策层", "全域"]:
            def empty_gen():
                yield f"⚠️ 在当前业务域 **[{filter_domain}]** 中未检索到相关资产。为防止幻觉，决策已拦截。请确认资产已同步至该目录。"

            return empty_gen(), []

        sources = list(set([doc.metadata.get("source", "未知来源") for doc in docs]))
        context_text = format_docs_with_source(docs)

        # 4. 🧠 Prompt：Matrix 人设维持
        template = """你是一个专业的保险业务智慧助手，隶属于 Matrix Intelligence 智能底座。
当前检索域：{domain_info}

【回答优先级指南】
1. **优先库内匹配**：如果[背景信息]中有直接相关的条款，请严谨回答。
2. **拒绝跨域猜测**：如果背景信息中没有答案，请诚实告知“无法根据现有底座资产给出建议”。
3. **专业人设**：维持保险助手的逻辑性，不编造。

[背景信息]:
{context}

[用户问题]:
{question}

回答："""

        prompt_text = ChatPromptTemplate.from_template(template)
        # 注意：此处 llm 已从 models.llm 导入
        chain = prompt_text | llm | StrOutputParser()

        def stream_generator():
            domain_info = filter_domain if filter_domain else "全域开放"
            # 使用 chain.stream 充分发挥 Ollama 的流式特性
            for chunk in chain.stream({
                "context": context_text,
                "question": query,
                "domain_info": domain_info
            }):
                yield chunk

        return stream_generator(), sources

    except Exception as e:
        error_info = str(e)
        logger.error(f"❌ Matrix 认知引擎执行异常: {error_info}")

        def err_gen():
            yield f"❌ 抱歉，Matrix 逻辑链路出现震荡: {error_info}"

        return err_gen(), []