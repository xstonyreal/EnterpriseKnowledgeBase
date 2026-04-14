# app/core/logger.py
import logging
import sys
from app.config import settings


def setup_logger():
    # 使用配置中的项目名作为 Logger 名称
    logger = logging.getLogger(settings.PROJECT_NAME)
    logger.setLevel(logging.DEBUG)

    # 防止在 Jupyter 或其他环境中重复添加 Handler 导致重复日志
    if not logger.handlers:
        # 创建控制台处理器
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)

        # 定义日志格式：时间 | 级别 | 消息
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        console_handler.setFormatter(formatter)

        # 将处理器添加到 logger
        logger.addHandler(console_handler)

    return logger


# 创建全局单例 logger
logger = setup_logger()