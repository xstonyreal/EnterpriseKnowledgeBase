# pipeline/watcher.py

import time
import os
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from app.config import settings
from app.core.logger import logger
from pathlib import Path
from app.utils.hash_utils import calculate_file_hash # 引入指纹

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
        # 1.过滤逻辑
        if os.path.basename(file_path).startswith(('.', '~', 'tmp')):
            return

        # 2. 冷却时间检查
        if time.time() - self.last_run < self.cooldown:
            return

        # 3. 保留核心感知和提醒：
        logger.info(f"✨ 监测到文件变动: {os.path.basename(file_path)}")

        # 缓冲 2 秒确保文件完整写入磁盘
        time.sleep(2)


        # 哨兵只提提醒，不执行全量切片入库
        # 停滞全量入库 ingest_documents()
        logger.info("📡 [哨兵] 已捕捉资产变动，待用户手动触发认知同步。")

        # 4. 更新运行时间，防止短时间内重复打印
        self.last_run = time.time()

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

# ***********************************
# 获取指纹 beginning
#************************************
def get_source_manifest(upload_dir: str) -> dict:
    """
    扫描目录并生成指纹清单
    返回格式: { "行政合规部/GL28.pdf": "md5_hash_string", ... }
    """
    manifest = {}
    base_path = Path(upload_dir)

    for file_path in base_path.rglob("*"):
        if file_path.is_file() and not file_path.name.startswith("."):
            # 获取相对路径并强制转换为 POSIX 风格 (正斜杠)
            relative_path = file_path.relative_to(base_path).as_posix()
            manifest[relative_path] = calculate_file_hash(file_path)

    return manifest
# ***********************************
# 获取指纹 ending
#************************************

if __name__ == "__main__":
    start_watcher()