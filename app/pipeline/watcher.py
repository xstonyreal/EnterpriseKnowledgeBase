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
# 保留導入（當前未使用，預留給未來自動觸發功能）
# 適配兩種運行方式：正常啟動 或 直接運行腳本
try:
    from app.pipeline.ingest import ingest_documents  # 完整項目路徑
except ImportError:
    from ingest import ingest_documents               # 腳本模式備份


class IngestHandler(FileSystemEventHandler):
    """监听文件生命周期事件（创建、修改、删除）"""

    def __init__(self):
        self.last_run = 0
        self.cooldown = 3

    def on_modified(self, event):
        if not event.is_directory:
            self._trigger(event.src_path, "变动")

    def on_created(self, event):
        if not event.is_directory:
            self._trigger(event.src_path, "新增")

    def on_deleted(self, event):
        if not event.is_directory:
            self._trigger(event.src_path,"移除")

    def _trigger(self, file_path, action_type):
        # 1.过滤逻辑
        """
        统一触发逻辑 (Single Trigger Entry)
        :param file_path: 触发事件的文件路径
        :param action_type: 事件语义标签 [新增/变动/移除]
        """
        file_name = os.path.basename(file_path)
        # 1. 静态过滤
        if file_name.startswith(('.', '~', 'tmp')) or file_name.endswith('.tmp'):
            return

        # 2. 冷却时间检查 (Debounce)
        if time.time() - self.last_run < self.cooldown:
            return

        # 3. 业务感知回响
        logger.info(f"✨ [哨兵感知] 资产入口发生{action_type}: {file_name}")

        # 4. 稳态等待：只有新增/变动需要等待 IO，移除直接通过
        if action_type != "移除":
            time.sleep(2)

        logger.info(f"📡 [哨兵] 已捕捉资产{action_type}，待用户手动触发认知同步。")

        # 5. 更新运行快照
        self.last_run = time.time()

def start_watcher():
    """獨立運行哨兵（用於測試，生產環境請使用 watcher_service.py）"""
    watch_dir = settings.DATA_UPLOAD_DIR
    if not os.path.exists(watch_dir):
        os.makedirs(watch_dir, exist_ok=True)

    event_handler = IngestHandler()
    observer = Observer()
    observer.schedule(event_handler, watch_dir, recursive=False) # recursive 如果多層目錄，應設置為 True

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


# *******確保哨兵旨在本應用被調用一次**********
if __name__ == "__main__":
    start_watcher()