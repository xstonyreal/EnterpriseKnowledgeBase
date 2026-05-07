# app/models/llm.py

import os
from langchain_ollama import ChatOllama
from app.config import settings


# ==========================================
# 判断.env 文件是否存在
# ==========================================
from app.core.logger import logger

def check_protocol_safety():
    env_path = ".env"
    if os.path.exists(env_path):
        # 获取修改时间，让你知道它是不是刚才新创的
        mtime = os.path.getmtime(env_path)
        logger.info(f"🛡️ 协议层确认：配置文件 {env_path} 稳固存在。")
    else:
        logger.warning("⚠️ 协议层警报：配置文件丢失！正在使用代码默认参数（易诱发 10054 报错）")

check_protocol_safety()
# ==========================================
# 判断.env 文件是否存在结束
# ==========================================
def get_llm():
    """
    【本地化加固】：初始化具备“耐力”与“边界”的 Ollama 引擎。
    针对本地显存环境，强制锁定上下文窗口，防止因 Token 溢出导致 10054 报错。
    """
    logger.info(f"🚀 正在挂载本地认知引擎: {settings.LLM_MODEL}")

    # 核心安全参数解释：
    # 1. num_ctx: 限制模型能“记住”的最大 Token 数。
    #    本地 8G 显存建议 4096，12G 以上可尝试 8192。
    # 2. timeout: 给本地模型留出足够的“思考时间”，防止推理过慢导致连接中断。

    llm = ChatOllama(
        model=settings.LLM_MODEL,
        base_url=settings.OLLAMA_BASE_URL,
        temperature=settings.LLM_TEMPERATURE,  # 建议从配置中读取
        num_ctx=settings.LLM_NUM_CTX,  # 👈 必须引用 settings，保持协议一致
        timeout=settings.LLM_TIMEOUT,  # 【关键】本地连接超时延长至 2分钟
        # repeat_penalty=1.1,      # 可选：防止模型复读机
    )

    return llm


# 全局单例：确保整个应用生命周期内，显存中只驻留一个模型实例
try:
    llm = get_llm()
    logger.info("✅ 本地认知引擎单例化成功")
except Exception as e:
    # 这里应用我们的“异常脱水”协议
    error_msg = str(e)
    logger.error(f"❌ 本地引擎启动失败: {error_msg}")
    llm = None