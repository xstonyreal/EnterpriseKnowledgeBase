# 異常脫水協議 (Exception Dehydration Protocol)

**版本**：v1.0  
**適用項目**：Matrix Intelligence  
**生效日期**：待確認  
**遷移策略**：漸進接入（新代碼遵守，老代碼逐步改造，亦可保持不變）

---

## 一、核心原則

> **捕獲即快照，延遲不引用**

禁止在任何生成器、延遲任務、異步回調中直接持有原始異常對象 `e` 的引用。所有異常必須在捕獲點立即轉化為**可序列化的字典結構**（脫水），後續鏈路只傳遞該字典。

### 為什麼？

| 場景 | 錯誤做法 | 後果 |
|------|----------|------|
| 生成器 `yield` | `yield {"error": e}` | `NameError: name 'e' is not defined`（生成器執行時 e 已銷毀） |
| 線程池提交 | `future = executor.submit(fn, e)` | 異常對象跨線程引用導致循環引用 |
| 日誌記錄 | `logger.error(e, exc_info=True)` | 某些場景下 `e` 被延遲格式化，丟失上下文 |

---

## 二、脫水數據結構（唯一傳遞格式）

所有異常在捕獲點必須轉化為以下 **dict 格式**：

```python
{
    "error": True,                    # 固定為 True，標識錯誤響應
    "code": "MODEL_OOM",              # 錯誤碼（見附錄）
    "message": "顯存不足，請重啟應用", # 用戶可讀的錯誤信息
    "recoverable": False,             # 是否可恢復（用於 UI 決策）
    "details": {                      # 可選，調試信息（不展示給用戶）
        "raw_type": "RuntimeError",
        "timestamp": "2026-01-15T10:30:00Z"
    }
}
禁止：在脫水後的 dict 中存儲原始異常對象（如 "exception": e）。

三、異常層級定義

# 基礎類（不直接拋出，供子類繼承）
MatrixBaseException
├── ConfigError          # 配置層錯誤（.env 缺失、路徑錯誤）
├── ModelLoadError       # 模型加載錯誤（OOM、模型不存在）
├── ConnectionError      # 物理層斷開（10054、Ollama 不可達）
├── RetrievalError       # 檢索層錯誤（FAISS 索引損壞、空結果）
├── IngestionError       # 入庫流水線錯誤（切片失敗、向量化失敗）
├── DomainIsolationError # 域隔離違規（跨域檢索嘗試）
└── UnhandledError       # 未分類原始異常（兜底）

錯誤碼列表
錯誤碼	對應異常	recoverable	UI 提示
CONFIG_ERROR	ConfigError	False	配置文件錯誤，請檢查 .env
MODEL_OOM	ModelLoadError	True	顯存不足，請重啟應用
MODEL_NOT_FOUND	ModelLoadError	False	本地模型未找到，請運行 ollama pull
CONNECTION_RESET	ConnectionError	True	模型服務中斷，檢查 Ollama 狀態
RETRIEVAL_FAILED	RetrievalError	False	檢索失敗，請重建索引
EMPTY_RESULT	RetrievalError	True	未找到相關內容，請嘗試其他關鍵詞
INGESTION_FAILED	IngestionError	False	文檔入庫失敗，請檢查文件格式
DOMAIN_VIOLATION	DomainIsolationError	False	違反數據隔離規則
RATE_LIMIT	MatrixBaseException	True	請求過頻，請稍後重試
TIMEOUT	MatrixBaseException	True	推理超時，請簡化問題或重試
UNHANDLED_ERROR	UnhandledError	False	系統錯誤，請查看日誌


四、逐層接入指南（低衝擊方案）
4.1 第一優先級：Pipeline 層的生成器
這是最容易出問題的地方，也是最優先需要改造的。

❌ 錯誤代碼（當前可能存在）：

python
def stream_process(self, files):
    for file in files:
        try:
            yield {"status": "success", "data": self._process(file)}
        except Exception as e:
            yield {"status": "error", "exception": e}  # ❌ 危險
✅ 正確代碼（改造後）：

python
def stream_process(self, files):
    for file in files:
        try:
            yield {"status": "success", "data": self._process(file)}
        except Exception as e:
            # ✅ 捕獲即脫水
            dehydrated = {
                "error": True,
                "code": "INGESTION_FAILED",
                "message": f"處理失敗: {file}",
                "recoverable": False,
                "details": {"raw": str(e)}
            }
            yield {"status": "error", **dehydrated}
4.2 第二優先級：Core 引擎層
❌ 錯誤代碼：

python
def query(self, question):
    try:
        return self.llm.invoke(question)
    except ConnectionError as e:
        raise e  # ❌ 直接上拋，未脫水
✅ 正確代碼：

python
def query(self, question):
    try:
        return self.llm.invoke(question)
    except ConnectionError as e:
        # ✅ 立即脫水，返回 dict
        return {
            "error": True,
            "code": "CONNECTION_RESET",
            "message": "模型服務連接中斷，請檢查 Ollama",
            "recoverable": True,
            "details": {"original": str(e)}
        }
4.3 第三優先級：Service 層
Service 層作為調度中樞，接收到底層的異常 dict 後直接透傳，不再重新包裝。

python
def some_service_method(self):
    result = self.engine.query(question)
    if isinstance(result, dict) and result.get("error"):
        # 直接透傳，不再加工
        return result
    return {"answer": result}
4.4 第四優先級：UI 層（Streamlit）
UI 層只處理脫水後的 dict，永遠不直接 st.exception(e)。

python
def display_response(response):
    if isinstance(response, dict) and response.get("error"):
        code = response.get("code")
        if code == "MODEL_OOM":
            st.error("⚠️ 顯存不足，請重啟應用或減少批處理數量")
        elif code == "CONNECTION_RESET":
            st.error("🔌 模型服務已斷開，請檢查 Ollama 是否運行")
        else:
            st.error(f"❌ {response.get('message')}")
    else:
        st.success(response.get("answer", response))
五、向現有代碼庫遷移的漸進策略
策略 A：新建 exceptions.py 但不立即啟用
python
# app/core/exceptions.py
# 第一步：只定義數據結構和常量，不修改任何業務代碼

ERROR_CODES = {
    "CONFIG_ERROR": {"message": "配置錯誤", "recoverable": False},
    "MODEL_OOM": {"message": "顯存不足", "recoverable": True},
    # ...
}
策略 B：在關鍵路徑添加「防護網」
在不改動現有邏輯的前提下，在生成器出口處增加攔截：

python
def safe_yield(generator):
    """包裝器：攔截生成器中的異常引用問題"""
    for item in generator:
        if isinstance(item, dict) and "exception" in item:
            # 發現潛在問題，轉換為安全格式
            item = {
                "error": True,
                "code": "UNHANDLED_ERROR", 
                "message": str(item["exception"]),
                "recoverable": False,
                "details": {}
            }
        yield item
策略 C：按模塊逐步改造（推薦進度）
階段	模塊	預計工作量	風險
第1週	pipeline/ingest.py（生成器）	2-3處改造	高（最容易出問題）
第2週	core/engine.py（檢索+LLM調用）	3-5處改造	中
第3週	services/（調度層）	4-6處改造	低
第4週	api/ + app_ui.py（展示層）	2-4處改造	低
重要提示：您可以選擇永遠不改造現有代碼。此協議僅用於指導未來新增的代碼。

六、自檢清單（接入完成後）
每次提交代碼前檢查：

所有 yield 語句所在函數的 except 塊中，是否有多於 yield 後引用 e 的情況？

所有 return 異常的地方，是否返回的是 dict 而非異常對象？

所有 st.exception() 或 print(e) 是否已移除？

錯誤碼是否使用了附錄中的預定義值？

七、附錄：錯誤碼快速查詢表
碼	含義	recoverable
CONFIG_ERROR	配置錯誤	❌
MODEL_OOM	顯存溢出	✅
MODEL_NOT_FOUND	模型不存在	❌
CONNECTION_RESET	連接中斷	✅
RETRIEVAL_FAILED	檢索失敗	❌
EMPTY_RESULT	空結果	✅
INGESTION_FAILED	入庫失敗	❌
DOMAIN_VIOLATION	域隔離違規	❌
RATE_LIMIT	頻率限制	✅
TIMEOUT	超時	✅
UNHANDLED_ERROR	未處理錯誤	❌

