# app/core/exceptions.py

"""
⚠️ 異常脫水協議（設計文檔）

本文件定義了統一的異常處理規範，用於指導未來新增代碼。
當前版本【暫不強制啟用】，現有代碼仍使用原有的異常處理方式。

啟用時機：待功能頁面穩定後，逐步遷移。

主要目標：
- 解決生成器中 yield 原始異常對象導致的 NameError
- 統一錯誤碼和用戶提示格式

使用示例（僅供參考，當前可不使用）：
    from app.core.exceptions import dehydrate_exception
    try:
        ...
    except Exception as e:
        yield dehydrate_exception(e, "處理失敗")
"""

from typing import Optional, Dict, Any

class MatrixBaseException(Exception):
    """Matrix Intelligence 統一異常基類"""
    def __init__(
            self,
            message: str,
            code: str = "INTERNAL_ERROR",
            details: Optional[Dict[str, Any]] = None
    ):
        self.message = message
        self.code = code
        self.details = details or {}
        super().__init__(self.message)

    def dehydrate(self) -> Dict[str, Any]:
        """脫水協議：捕獲即快照，生成用戶可感知的錯誤信息"""
        return {
            "error": True,
            "code": self.code,
            "message": self.message,
            "recoverable": self._is_recoverable()
        }

    def _is_recoverable(self) -> bool:
        recoverable_codes = {"RATE_LIMIT", "TIMEOUT", "EMPTY_RESULT", "CONNECTION_RESET"}
        return self.code in recoverable_codes

def dehydrate_exception(e: Exception, message: str = "引擎處理失敗") -> Dict[str, Any]:
    """將原生異常轉化為脫水 JSON 字典"""
    return {
        "error": True,
        "code": type(e).__name__,
        "message": message,
        "details": {"raw": str(e)}
    }