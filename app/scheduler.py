# scheduler .py

"""
定时任务模块 - 每日凌晨 2:00 全量重建 FAISS 索引

用途：
    定期清理索引中的墓碑标记（已删除文件），压缩索引体积，保持长期稳定性。

部署环境：
    - 支持普通 Python 脚本
    - 支持 Streamlit 多会话环境（使用 session_state 防止重复启动）

依赖：
    apscheduler>=3.10.0
"""

import streamlit as st
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from app.core.logger import logger

# --- [ 核心對齊：導入類並實例化 ] ---
from app.services.ingest_service import IngestService
ingest_manager = IngestService()

# 全局调度器实例（模块级，仅在首次导入时创建）
_scheduler = None


def start_daily_rebuild():
    """
    启动每日凌晨 2:00 的全量重建定时任务

    特性：
        1. 使用 Streamlit session_state 确保全局只启动一次
        2. 支持多会话/多进程环境（通过模块级变量 + session_state 双重防护）
        3. 应用退出时自动清理调度器资源
    """
    global _scheduler

    # ========== 第一层防护：session_state（防止 Streamlit 重跑时重复启动）==========
    if "scheduler_started" not in st.session_state:
        st.session_state.scheduler_started = False

    if st.session_state.scheduler_started:
        logger.debug("⏰ [定时任务] 调度器已在运行中，跳过重复启动（session_state 拦截）")
        return

    # ========== 第二层防护：模块级变量（防止多线程/多会话竞争）==========
    if _scheduler is not None:
        logger.debug("⏰ [定时任务] 调度器实例已存在，跳过重复启动（模块变量拦截）")
        st.session_state.scheduler_started = True
        return

    # ========== 创建并启动调度器 ==========
    try:
        _scheduler = BackgroundScheduler()

        # 添加每日凌晨 2:00 执行的全量重建任务
        _scheduler.add_job(
            func=_full_rebuild_job,
            trigger=CronTrigger(hour=2, minute=0),
            id="daily_faiss_rebuild",
            replace_existing=True,
            name="每日全量索引重建"
        )

        # 启动调度器
        _scheduler.start()

        # 标记已启动
        st.session_state.scheduler_started = True

        logger.info("⏰ [定时任务] 调度器已启动 - 每日 02:00 执行全量索引重建")

        # ========== 注册退出清理 ==========
        import atexit
        atexit.register(_shutdown_scheduler)

    except Exception as e:
        logger.error(f"❌ [定时任务] 调度器启动失败: {e}")
        st.session_state.scheduler_started = False
        _scheduler = None


def _full_rebuild_job():
    """定時任務執行函數"""
    try:
        logger.info("🔄 [定時任務] 開始執行每日全量索引重建...")

        # ✅ 修復：通過實例對象 ingest_manager 調用類方法
        vectorstore = ingest_manager.initialize_knowledge_base(force_rebuild=True)

        if vectorstore is not None:
            logger.info("✅ [定時任務] 每日全量索引重建完成")
        else:
            logger.warning("⚠️ [定時任務] 全量索引重建返回 None，請檢查數據源")

    except Exception as e:
        logger.error(f"❌ [定時任務] 全量索引重建失敗: {e}", exc_info=True)


def _shutdown_scheduler():
    """
    关闭调度器（应用退出时自动调用）
    """
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("⏰ [定时任务] 调度器已关闭")


def trigger_manual_rebuild():
    """
    手动触发全量重建（供 UI 按钮调用）
    """
    logger.info("🔧 [手动触发] 开始执行全量索引重建...")
    # ✅ 修復：同樣改用實例化調用，不再直接調用未導入的全局函數
    return ingest_manager.initialize_knowledge_base(force_rebuild=True)