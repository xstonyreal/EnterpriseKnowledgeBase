# app/services/watcher_service.py
import threading
import time
from app.pipeline.watcher import IngestHandler
from app.config import settings
from app.core.logger import logger
from watchdog.observers import Observer


class SentinelThread(threading.Thread):
    """
    将 Watchdog 封装在守护线程中，
    使其能随 App 启动而启动，随 App 关闭而优雅退出。
    """

    def __init__(self):
        super().__init__()
        self.daemon = True  # 守护线程，主程序结束它自动结束
        self.observer = Observer()
        self.stop_event = threading.Event()

    def run(self):
        watch_dir = settings.DATA_UPLOAD_DIR
        event_handler = IngestHandler()
        self.observer.schedule(event_handler, watch_dir, recursive=False)

        logger.info(f"📡 哨兵服务已在后台激活，监控域: {watch_dir}")
        self.observer.start()

        try:
            while not self.stop_event.is_set():
                time.sleep(1)
        finally:
            self.observer.stop()
            self.observer.join()


def start_sentinel():
    """入口函数：启动后台监控"""
    sentinel = SentinelThread()
    sentinel.start()
    return sentinel