# app/models/llm.py
from langchain_ollama import ChatOllama
from app.config import settings
from app.core.logger import logger


def get_llm():
    logger.info(f"初始化 LLM: {settings.LLM_MODEL}")

    llm = ChatOllama(
        model=settings.LLM_MODEL,
        base_url=settings.OLLAMA_BASE_URL,
        temperature=0.7,
    )

    return llm


# 全局单例，避免重复初始化
llm = get_llm()