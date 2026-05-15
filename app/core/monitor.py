# app/core/monitor.py

import time
import json
import functools
from app.core.logger import logger

class Monitor:
    @staticmethod
    def log_metrics(module: str, action: str, metrics: dict, extra: dict = None):
        """核心輸出：機器可解析的結構化日誌"""
        payload = {
            "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
            "mod": module,
            "act": action,
            "met": metrics,
            "ext": extra or {}
        }
        # 使用固定前綴，方便後續 grep 和自動化分析
        logger.info(f"📊 [METRICS] {json.dumps(payload, ensure_ascii=False)}")

    @staticmethod
    def track_stream(module, action):
        def decorator(func):
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                start = time.perf_counter()
                # 獲取生成器
                gen, results, metrics = func(*args, **kwargs)

                def monitored_gen():
                    first_token_sent = False
                    for item in gen:
                        if not first_token_sent:
                            # 這裡才是真正的「首字響應」
                            ttft = int((time.perf_counter() - start) * 1000)
                            logger.info(f"⚡ [REAL_TTFT] {ttft}ms")
                            first_token_sent = True
                        yield item
                    # 結束時記錄總耗時
                    total = int((time.perf_counter() - start) * 1000)
                    Monitor.log_metrics(module, action, {"total_ms": total})

                return monitored_gen(), results, metrics

            return wrapper

        return decorator