# pipeline/watcher.py

import time
import os
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from app.config import settings
from app.core.logger import logger

# 适配位置：从同包或完整路径导入
try:
    from app.pipeline.ingest import ingest_documents
except ImportError:
    from ingest import ingest_documents


class IngestHandler(FileSystemEventHandler):
    """监听文件创建和修改事件"""

    def __init__(self):
        self.last_run = 0
        self.cooldown = 3

    def on_modified(self, event):
        if not event.is_directory:
            self._trigger(event.src_path)

    def on_created(self, event):
        if not event.is_directory:
            self._trigger(event.src_path)

    def _trigger(self, file_path):
        if os.path.basename(file_path).startswith(('.', '~', 'tmp')):
            return

        if time.time() - self.last_run < self.cooldown:
            return

        logger.info(f"✨ 监测到文件变动: {os.path.basename(file_path)}")
        # 缓冲 2 秒确保文件完整写入磁盘
        time.sleep(2)
        try:
            ingest_documents()
            self.last_run = time.time()
        except Exception as e:
            logger.error(f"❌ 自动入库失败: {e}")


def start_watcher():
    watch_dir = settings.DATA_UPLOAD_DIR
    if not os.path.exists(watch_dir):
        os.makedirs(watch_dir, exist_ok=True)

    event_handler = IngestHandler()
    observer = Observer()
    observer.schedule(event_handler, watch_dir, recursive=False)

    logger.info(f"📡 自动入库哨兵启动 (Pipeline模式)，监控: {watch_dir}")
    observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()


if __name__ == "__main__":
    start_watcher()