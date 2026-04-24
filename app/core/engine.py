# app/core/engine.py

import os
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

# 统一从 models 引入单例
from app.models.llm import llm
from app.config import settings
from app.core.logger import logger
# 统一使用底座定义的服务
from app.services.ingest_service import initialize_knowledge_base


def format_docs_with_source(docs):
    """
    格式化检索到的文档：
    为 Prompt 提供清晰的上下文边界，同时在 Metadata 中保留分域信息。
    """
    parts = []
    for i, doc in enumerate(docs):
        # 仅保留文件名作为 Prompt 标识，减少 Token 浪费
        source = os.path.basename(doc.metadata.get("source", "未知来源"))
        domain = doc.metadata.get("domain", "通用")
        # 清洗换行符，防止破坏 Prompt 结构
        content = doc.page_content.replace('\n', ' ').strip()
        parts.append(f"--- 资料项 {i + 1} [领域: {domain} | 来源: {source}] ---\n{content}")
    return "\n\n".join(parts)


def get_chat_response_stream(query: str, filter_domain: str = None):
    """
    Matrix Intelligence 增强版流式引擎：
    1. 支持 FAISS 相似度得分回传。
    2. 支持 UI 端的溯源预览卡片。
    3. 严格分域隔离拦截。
    """
    # 初始化/获取底座单例
    db = initialize_knowledge_base()

    if db is None:
        def err_gen(): yield "❌ Matrix 底座未就绪，请先执行资产同步。"

        return err_gen(), []

    query_l = query.lower().strip()

    # 1. 极简社交拦截
    pure_greetings = ["hello", "hi", "你好", "哈喽", "在吗", "嗨", "早上好", "下午好"]
    if query_l in pure_greetings:
        def greeting_gen():
            yield f"您好！我是您的业务智慧助手。当前业务域：`{filter_domain or '全域'}`。"

        return greeting_gen(), []

    try:
        # 2. 🔍 精准检索：获取文档 + 分数
        search_kwargs = {"k": settings.TOP_K}

        # 注入过滤：实现“文件夹即权限”的物理隔离
        if filter_domain and filter_domain not in ["核心决策层", "未分类资产", "全域"]:
            search_kwargs["filter"] = {"domain": filter_domain}
            logger.info(f"🎯 [精准模式] 检索域锁定: {filter_domain}")
        else:
            logger.info("🌐 [全域模式] 执行跨域语义检索...")

        # 【核心修改】：从单纯搜索改为“带分数搜索”
        # docs_and_scores 格式: [(doc, score), ...]
        docs_and_scores = db.similarity_search_with_score(query, **search_kwargs)

        # 3. 🛑 零知识拦截与数据封装
        if not docs_and_scores:
            def empty_gen(): yield f"⚠️ 在业务域 **[{filter_domain}]** 中未发现相关线索，已拦截幻觉输出。"

            return empty_gen(), []

        # 【契约重构】：封装 sources 字典列表，供 UI 渲染增强卡片
        sources = []
        seen_sources = set()
        for doc, score in docs_and_scores:
            src_path = doc.metadata.get("source", "未知来源")
            # 记录来源：去重显示，但保留前 N 个最相关的片段摘要
            if src_path not in seen_sources or len(sources) < 3:
                sources.append({
                    "source": src_path,
                    "score": float(score),  # FAISS 返回 L2 距离
                    "content": doc.page_content.strip()[:150]  # 截取 150 字预览
                })
                seen_sources.add(src_path)

        # 4. 🧠 注入上下文并生成 Prompt
        docs = [d[0] for d in docs_and_scores]  # 提取 Document 对象供格式化
        context_text = format_docs_with_source(docs)

        template = """你是一个专业的智慧助手，隶属于 Matrix Intelligence 智能底座。
当前检索域：{domain_info}

【回答规则】
1. **基于事实**：仅使用[背景信息]中的内容回答。
2. **严谨溯源**：如果引用了资料，请在回答中尽量保持客观。
3. **诚实原则**：如果背景信息不足，直接回答“抱歉，底座中暂无相关业务记录”。

[背景信息]:
{context}

[用户问题]:
{question}

回答："""

        prompt_text = ChatPromptTemplate.from_template(template)
        chain = prompt_text | llm | StrOutputParser()

        def stream_generator():
            domain_info = filter_domain if filter_domain else "全域开放"
            for chunk in chain.stream({
                "context": context_text,
                "question": query,
                "domain_info": domain_info
            }):
                yield chunk

        return stream_generator(), sources

    except Exception as e:
        logger.error(f"❌ 引擎执行异常: {str(e)}", exc_info=True)

        def err_gen():
            yield f"❌ 链路震荡: {str(e)}"

        return err_gen(), []


def get_chat_response(query: str, filter_domain: str = None) -> str:
    """CLI/同步兼容层"""
    stream_gen, sources = get_chat_response_stream(query, filter_domain)
    full_response = "".join(list(stream_gen))
    return full_response