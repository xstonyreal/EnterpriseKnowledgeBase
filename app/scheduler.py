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
from app.services.ingest_service import initialize_knowledge_base

# 全局调度器实例（模块级，仅在首次导入时创建）
_scheduler = None


def start_daily_rebuild():
    """
    启动每日凌晨 2:00 的全量重建定时任务

    特性：
        1. 使用 Streamlit session_state 确保全局只启动一次
        2. 支持多会话/多进程环境（通过模块级变量 + session_state 双重防护）
        3. 应用退出时自动清理调度器资源

    调用位置：
        在 app_ui.py 或主入口文件中调用一次即可
        例如：start_daily_rebuild()
    """
    global _scheduler

    # ========== 第一层防护：session_state（防止 Streamlit 重跑时重复启动）==========
    # Streamlit 每次交互都会重跑整个脚本，使用 session_state 标记已启动状态
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
    """
    定时任务执行函数：全量重建索引

    说明：
        由调度器在后台线程中调用，不阻塞主业务流程。
    """
    try:
        logger.info("🔄 [定时任务] 开始执行每日全量索引重建...")

        # force_rebuild=True 会清空现有索引并基于 manifest 全量重建
        # check_manifest 在 force_rebuild 模式下被忽略
        vectorstore = initialize_knowledge_base(force_rebuild=True)

        if vectorstore is not None:
            logger.info("✅ [定时任务] 每日全量索引重建完成")
        else:
            logger.warning("⚠️ [定时任务] 全量索引重建返回 None，请检查数据源")

    except Exception as e:
        logger.error(f"❌ [定时任务] 全量索引重建失败: {e}", exc_info=True)


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

    用途：
        除了定时任务外，管理员可通过此函数手动触发重建
    """
    logger.info("🔧 [手动触发] 开始执行全量索引重建...")
    return initialize_knowledge_base(force_rebuild=True)