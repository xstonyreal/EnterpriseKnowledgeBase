# app/core/logger.py

import logging
import sys
from app.config import settings


def setup_logger():
    """配置並返回全局 Logger 實例"""
    logger = logging.getLogger(settings.PROJECT_NAME)

    # 從配置讀取日誌級別，默認 INFO
    log_level_str = getattr(settings, "LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_str, logging.INFO)

    logger.setLevel(log_level)
    logger.propagate = False

    if not logger.handlers:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(log_level)

        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        console_handler.setFormatter(formatter)

        logger.addHandler(console_handler)

    return logger


logger = setup_logger()
