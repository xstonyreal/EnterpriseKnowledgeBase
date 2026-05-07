# app/api/chat.py
import os
from app.config import settings
from app.models.llm import llm
from app.core.logger import logger
from app.services.ingest_service import initialize_knowledge_base
# [核心引入] 對接你剛剛寫好的混合檢索工廠函數
from app.services.search_service import do_hybrid_search

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough, RunnableParallel
from langchain_core.documents import Document

# ==========================================
# 1. 核心問答鏈構建引擎 (混合動力版)
# ==========================================

def get_qa_chain(domain: str = None):
    """
    【LCEL 混合檢索架構】
    將檢索環節替換為自定義的 do_hybrid_search (BM25 + Vector)
    """
    try:
        # 確保單例已初始化 (雖然 SearchService 內部也會檢查，但這是 Matrix 架構的安全防護)
        initialize_knowledge_base()

        # [修改點 1] 定義適配器：將混合檢索的 Dict 結果轉為 LangChain Document
        def hybrid_retriever_adapter(query_text: str):
            """
            調用 search_service.py 中的混合檢索
            """
            raw_results = do_hybrid_search(
                query=query_text,
                domain=domain,
                top_k=settings.TOP_K
            )
            # 將 Dict 轉回 Document 對象，否則 prompt 無法解析 {context}
            return [
                Document(page_content=r["content"], metadata=r["metadata"])
                for r in raw_results
            ]

        # 提示詞模板
        template = """基于以下已知信息，简洁和专业地回答用户的问题。如果无法从中得到答案，请说“根据已知信息无法回答该问题”。

已知信息：
{context}

用户问题：{question}

回答："""
        prompt = ChatPromptTemplate.from_template(template)

        # [修改點 2] 構建 LCEL 並行鏈條
        # 使用 RunnableParallel 保留檢索到的文檔，用於後續 sources 的展示
        qa_chain = (
            RunnableParallel({
                "context": hybrid_retriever_adapter, # 注入混合動力引擎
                "question": RunnablePassthrough()
            })
            | {
                "answer": prompt | llm | StrOutputParser(),
                "sources": lambda x: x["context"]
            }
        )

        logger.info(f"🚀 [混合動力] 問答引擎掛載完成 | 域感知: {domain or '全局'}")
        return qa_chain

    except Exception as e:
        logger.error(f"🚨 鏈條構建失敗: {str(e)}", exc_info=True)
        return None


# ==========================================
# 2. 業務調用接口
# ==========================================

def ask_question(query: str, domain: str = None):
    """
    核心業務接口：支持跨域混合檢索問答
    """
    logger.info(f"🔍 [混合請求] 域: {domain or '全局'} | 問題: {query}")

    chain = get_qa_chain(domain=domain)
    if not chain:
        return {"answer": "❌ 系統未初始化，請先點擊「同步」按鈕。", "sources": []}

    try:
        # 執行調用
        # 此處返回的是個字典: {"answer": "...", "sources": [Document, ...]}
        result = chain.invoke(query)

        # 提取結果
        answer = result.get("answer", "無回答內容")
        source_docs = result.get("sources", [])

        # 提取來源標籤並去重
        sources = list(set([doc.metadata.get("source", "未知文件") for doc in source_docs]))

        logger.success(f"✅ 生成完畢 (混合檢索命中片段: {len(source_docs)})")

        return {
            "answer": answer,
            "sources": sources
        }

    except Exception as e:
        logger.error(f"❌ 問答執行出錯: {str(e)}")
        return {"answer": f"處理出錯: {str(e)}", "sources": []}


# ==========================================
# 3. 本地測試代碼
# ==========================================

if __name__ == "__main__":
    print("\n" + "★" * 25)
    print("🤖 Matrix Hybrid RAG 測試沙盒")
    print("★" * 25 + "\n")

    # 模擬測試域
    test_domain = "核心决策层"

