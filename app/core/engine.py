# app/core/engine.py
import os
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.documents import Document  # 新增：用於封裝混合檢索結果
import time  # 獲取耗時
from typing import Generator, List, Dict, Any, Tuple
from app.services import search_service, rerank_service
from app.core.logger import logger
from app.core.monitor import Monitor

# 统一从 models 引入单例
from app.models.llm import get_cached_llm, settings
from app.config import settings
from app.core.logger import logger
# --- [M3 核心注入] ---
# 引入我們剛剛建立的混合檢索服務
from app.services.search_service import SearchService
from app.services.rerank_service import get_rerank_service  # rerank




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

# 引入埋點
@Monitor.track_stream(module="Engine", action="chat_response")
def get_chat_response_stream(query: str, filter_domain: str) -> Tuple[Generator, List[Any], Dict[str, str]]:
    """
    Matrix Intelligence 混合檢索增強版流式引擎：
    1. 實裝 RRF 混合檢索 (FAISS + BM25)。
    2. 支持 UI 端的溯源預覽卡片。
    3. 嚴格執行「文件夾即權限」的業務域過濾。
    """
    """
    獲取聊天響應流，並增加鏈路耗時追蹤
    """
    metrics = {}  # === [ADDED] 用於存儲性能埋點數據 ===
    # 問答日志在終端的展示
    logger.info(f"💬 用户提问：{query}")
    logger.info(f"📂 业务域：{filter_domain}")

    # --- [獲取懶加載的模型實例] ---
    # 只有進入此對話函數時，才會觸發 SearchService 和 LLM 的加載
    search_svc = SearchService()
    llm = get_cached_llm()
    if not llm:
        def error_init_gen(): yield "❌ 模型初始化失敗，請檢查後台日誌或 Ollama 狀態。"

        return error_init_gen(), [], metrics

    query_l = query.lower().strip()

    # 1. 极简社交拦截
    pure_greetings = ["hello", "hi", "你好", "哈喽", "在吗", "嗨", "早上好", "下午好"]
    if query_l in pure_greetings:
        def greeting_gen():
            yield f"您好！我是您的业务智慧助手。当前业务域：`{filter_domain or '全域'}`。"

        return greeting_gen(), [], metrics  # === [MODIFIED] 返回空 metrics ===

    try:
        # === [ADDED] 開始檢索追蹤 ===
        start_search = time.perf_counter()

        # 2. 🔍 [核心變動]：執行混合檢索，獲取 RRF 融合結果
        # top_n 取 settings.TOP_K * 2，為後續的 Domain 過濾預留空間
        # 使用局部實例化的  search_svc   執行檢索
        # raw_results , search_metrics= search_svc.hybrid_search(query, top_n=settings.TOP_K * 2)
        # 强制取一條
        raw_results, search_metrics = search_svc.hybrid_search(query, top_n=1)

        #  metrics 字典包含像 "vector_ms", "bm25_count" 等具體數據
        metrics.update(search_metrics)

        # === [ADDED] 記錄檢索耗時 ===
        metrics["檢索耗時"] = f"{(time.perf_counter() - start_search) * 1000:.0f}ms"

        if not raw_results:
            def empty_gen(): yield f"⚠️ 在業務域 **[{filter_domain}]** 中未發現相關線索，已攔截幻覺輸出。"

            return empty_gen(), [], metrics  # === [MODIFIED] ===

        # 2.5 🎯 新增：Rerank 重排序（精排）
        if settings.ENABLE_RERANK and raw_results and len(raw_results) > settings.TOP_K:
            # === [ADDED] 開始精排追蹤 ===
            start_rerank = time.perf_counter()
            try:
                reranker = get_rerank_service()
                raw_results = reranker.rerank(query, raw_results, top_n=settings.TOP_K * 2)
                # === [ADDED] 記錄精排耗時 ===
                metrics["精排耗時"] = f"{(time.perf_counter() - start_rerank) * 1000:.0f}ms"
            except Exception as e:
                logger.warning(f"Rerank 失败，使用原结果: {e}")
                metrics["精排耗時"] = "Fail"  # === [ADDED] ===

        # 3. 🛡️ 業務域隔離過濾
        sources = []
        filtered_docs = []

        for res in raw_results:
            content = res["content"]
            metadata = res["metadata"]
            score = res["score"]  # 注意：這是 RRF 分數
            src_path = metadata.get("source", "未知來源")

            # 從路徑解析業務域（與 ingest 邏輯一致）
            # 假設路徑結構為 data/uploads/業務域/文件名
            doc_domain = metadata.get("domain", "未分類資產")

            # 邏輯攔截：匹配「全域」、「核心決策層」或指定的「filter_domain」
            if not filter_domain or filter_domain in ["核心决策层", "未分类资产",
                                                      "全域"] or filter_domain == doc_domain:
                # 封裝 UI 溯源卡片數據
                sources.append({
                    "source": src_path,
                    "score": float(score),
                    "content": content.strip()[:150]  # 截取預覽
                })
                # 封裝 Document 對象供後續 format_docs_with_source 使用
                filtered_docs.append(Document(page_content=content, metadata=metadata))

        # 二次檢查過濾後的結果
        if not filtered_docs:
            def empty_gen(): yield f"⚠️ 該關鍵詞在當前業務域 **[{filter_domain}]** 無匹配項。"

            return empty_gen(), [], metrics  # === [MODIFIED] ===

        # 4. 🧠 注入上下文並生成 Prompt
        # 取前 settings.TOP_K 個最相關的片段餵給 LLM
        # context_text = format_docs_with_source(filtered_docs[:settings.TOP_K])
        # 强制取一條
        context_text = format_docs_with_source(filtered_docs[:1])

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
            # === [ADDED] 標記 LLM 開始渲染時間 ===
            start_llm = time.perf_counter()
            first_chunk = True

            for chunk in chain.stream({
                "context": context_text,
                "question": query,
                "domain_info": domain_info
            }):
                if first_chunk:
                    # 記錄首字響應延遲 (TTFT)
                    ttft = (time.perf_counter() - start_llm) * 1000
                    logger.info(f"📏 Prompt 字符數: {len(context_text) + len(query)}")
                    logger.info(f"⚡ LLM 首字響應: {ttft:.0f}ms")
                    first_chunk = False
                yield chunk

        # 增加UI界面成功標志

        return stream_generator(), sources, metrics  # === [MODIFIED] 返回三元組 ===

    except Exception as e:
        error_info = str(e)
        logger.error(f"❌ 引擎执行异常: {error_info}", exc_info=True)

        def err_gen():
            yield f"❌ 链路震荡: {error_info}"

        return err_gen(), [], metrics  # === [MODIFIED] ===


def get_chat_response(query: str, filter_domain: str = None) -> str:
    """CLI/同步兼容层"""
    # === [MODIFIED] 兼容三元組返回值 ===
    stream_gen, sources, metrics = get_chat_response_stream(query, filter_domain)
    full_response = "".join(list(stream_gen))
    return full_response