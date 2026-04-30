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


# ========== 基礎異常類 ==========

class MatrixBaseException(Exception):
    """Matrix Intelligence 統一異常基類"""

    def __init__(
            self,
            message: str,
            code: str = "INTERNAL_ERROR",
            details: Optional[Dict[str, Any]] = None,
            original_exception: Optional[Exception] = None
    ):
        self.message = message
        self.code = code
        self.details = details or {}
        self.original_exception = original_exception
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
        """判斷錯誤是否可恢復"""
        recoverable_codes = {"RATE_LIMIT", "TIMEOUT", "EMPTY_RESULT", "CONNECTION_RESET"}
        return self.code in recoverable_codes


# ========== 具體異常類型 ==========

def dehydrate_exception(e: Exception, message: str = "處理失敗") -> Dict[str, Any]:
    """將異常轉為可安全傳遞的字典"""
    return {
        "error": True,
        "code": type(e).__name__,
        "message": message,
        "details": {"raw": str(e)}
    }


def make_error_response(code: str, message: str) -> Dict[str, Any]:
    """快速構造錯誤響應"""
    return {
        "error": True,
        "code": code,
        "message": message
    }