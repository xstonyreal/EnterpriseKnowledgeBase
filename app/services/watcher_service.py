# app/services/watcher_service.py
import threading
import time
from app.pipeline.watcher import IngestHandler
from app.config import settings
from app.core.logger import logger
from watchdog.observers import Observer

# [架构级锁定]：哨兵单例句柄。
# 作用：确保整个 App 生命周期内只有一个监控线程在运行，防止日志刷屏和 CPU 占用过高。
_SENTINEL_INSTANCE = None


class SentinelThread(threading.Thread):
    """
    将 Watchdog 封装在异步守护线程中：
    使其能够实时感应 DATA_UPLOAD_DIR 目录的文件变化。
    """

    def __init__(self):
        super().__init__()
        # 设置为守护线程：当主 UI 进程关闭时，哨兵会随之自动销毁，不残留后台进程
        self.daemon = True
        self.observer = Observer()
        self.stop_event = threading.Event()

    def run(self):
        watch_dir = settings.DATA_UPLOAD_DIR
        # IngestHandler 是具体的处理逻辑，负责在文件变动时触发增量入库
        event_handler = IngestHandler()

        # ======================================================================
        # 【核心架构逻辑：深度递归监控】
        # 参数说明: recursive=True
        # ----------------------------------------------------------------------
        # 1. 业务逻辑背景：我们采用了“子文件夹 = 业务域 (Domain)”的物理隔离架构。
        # 2. 赋值必要性：如果设为 False，监控器将只盯着 uploads 根目录，而无法感知落入
        #    子目录（如 uploads/财务部/）的新增资产，导致“盲区”。
        # 3. 确定性保障：开启递归模式后，哨兵能穿透监控到所有层级的部门文件夹。
        # 4. 噪音控制：通过 IngestHandler 内部的后缀过滤逻辑来排除系统干扰文件。
        # ======================================================================
        self.observer.schedule(event_handler, watch_dir, recursive=True)

        logger.info(f"📡 [哨兵激活] 正在实时监控资产入口: {watch_dir}")
        self.observer.start()

        try:
            # 进入静默监控循环，低频检测停止信号
            while not self.stop_event.is_set():
                time.sleep(1)
        except Exception as e:
            logger.error(f"⚠️ [哨兵异常] 实时监控链路中断: {e}")
        finally:
            self.observer.stop()
            self.observer.join()


def start_sentinel():
    """
    入口函数：启动后台监控逻辑。
    通过全局锁机制，确保 Streamlit 的“重绘”不会触发重复的监听线程。
    """
    global _SENTINEL_INSTANCE

    # 【逻辑拦截】：如果哨兵已经在岗，保持静默，不重复启动
    if _SENTINEL_INSTANCE is not None:
        return _SENTINEL_INSTANCE

    # 首次启动，执行实例化
    sentinel = SentinelThread()
    sentinel.start()
    _SENTINEL_INSTANCE = sentinel
    return _SENTINEL_INSTANCE