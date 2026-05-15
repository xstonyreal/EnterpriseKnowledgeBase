📅 Matrix Intelligence 本周执行计划 (2026.04.20 - 2026.04.26)

阶段一：压力测试与“边界感”验收 (Day 1-2)
* 任务 A：跨域污染深度自检。在不同 Domain 文件夹存放类似命名的文件，验证 Filter 逻辑在极端情况（重名文件、空文件夹）下的稳定性。

* 任务 B：Token 负载优化。由于目前采用 Full Rebuild（全量重构），需测试当单次上传超过 50MB 时的系统响应速度，并优化 ingest_service 的多线程处理。
    任务分解：从 并发处理、原子化向量化 和 计算分流 三个维度进行重构
    1. 引入多线程并行处理 (Multi-threading)
       目前的 ingest 是一份文件处理完再处理下一份。我们要将其改为基于 ThreadPoolExecutor 的并发模式。

       优化逻辑：将“读取-切片-向量化”这一整套动作封装为原子函数，利用多线程同时处理多个 Domain 下的文件。

       注意点：由于向量化（Embedding）通常涉及网络请求（OpenAI API），多线程能极大抵消网络延迟。

    2. Token 精准预算与动态分片
        为了防止单次 Payload 过大导致 API 报错（429 Too Many Requests 或 Context Length Exceeded），我们需要在 Service 层加入“预算控制”。

        优化逻辑：引入 tiktoken 对每个 Chunk 进行严格的 Token 计数。

        策略：如果单批次 Token 总量超过阈值，自动进行“批次提交（Batching）”，而不是一次性塞给服务器。

    3. 结构化重构：app/services/ingest_service.py

* 目标：确保“手术刀”在面对大数据量时依然精准不颤抖。

阶段二：交互深度进化 (Day 3)
* 任务 A：溯源增强卡片。在“认知溯源”中不仅显示文件名，还要显示匹配得分 (Similarity Score) 和原文页码/段落锚点。

* 任务 B：流式动画微调。优化 app_ui.py 的加载动画（Spinner），在执行“全量索引审计”时提供更明确的进度条。

* 目标：提升商业用户对系统的“掌控感”。

阶段三：高级语义工具链集成 (Day 4)
* 任务 A：引入“混合搜索”预研。在向量检索的基础上，尝试挂载关键词（Keyword）检索服务，解决特定专业名词（如保险条款编号）搜不准的问题。

* 任务 B：智能建议 (Suggestion) 功能。在对话结束后，让 AI 自动生成 3 个相关的后续问题，引导用户深入挖掘资产。

* 目标：让应用从“被动问答”转向“主动引导”。

阶段四：安全性与身份识别预留 (Day 5)
* 任务 A：Session 状态持久化。确保用户刷新网页后，当前选中的 Domain 和对话上下文不会瞬间丢失（通过 SQLite 或 SessionState 深度绑定）。

* 任务 B：API 路由化准备。利用我们在 services/ 做的抽象，尝试写一个简单的 FastAPI 接口，实现“代码与 UI 彻底分离”。

* 目标：为下周的“身份识别”与“多端接入”铺路。

🚩 本周里程碑交付物
全量重塑压力报告：确定系统承载资产的上限。

溯源增强版 UI：具备得分显示与高亮定位的交互界面。

Matrix API 接口规格书：定义好 ingest 和 query 的标准接口规范。

# ********************************
# 20260420
# *********************************
完成了从“单体脚本”向**“工业级分域 RAG 架构”**的跨越，核心成果涵盖以下四个维度：

1. 核心架构：服务化与单例治理
服务化重构：引入 app/services/ingest_service.py，将资产管理逻辑从业务逻辑中抽离。

单例模式锁定：通过全局变量与缓存机制，确保了向量库（FAISS）在内存中仅存在一份实例，彻底解决了多头加载导致的显存溢出风险。

自省式启动：main.py 具备了自感知能力，能自动根据本地索引状态决定是执行“1秒热加载”还是“全量重塑”。

2. 注入引擎：高性能并发重塑
并行解析系统：利用 ThreadPoolExecutor 实现了多线程文档解析，极大缩短了 50MB 级保险业务资产的处理耗时（299s 达标）。

内存负载护航：通过 INGEST_BATCH_SIZE 配置，将近千个切片分批次送入 Embedding 模型，确保了本地低算力环境下的稳定性。

分域标签注入：在 Ingest 阶段自动根据物理目录映射 domain 标签，为“分域隔离”提供了底层的物理依据。

3. 认知引擎：分域隔离与上帝视角
检索策略升级：app/core/engine.py 现在支持精准的 Metadata Filter。

精准模式：支持针对特定部门（如行政合规部）的定向检索。

上帝视角：默认开启全域语义搜索，支持跨部门知识聚合。

指令响应标准化：封装了带溯源能力的 Prompt 模板，强化了模型“不编造、不幻觉”的专业人设。

4. 配置协议：解耦与安全
Pydantic 协议层：统一了 config.py 管理，支持从 .env 动态覆盖。

环境变量治标：明确了配置优先级（ENV > .env > Default），确保了开发环境与生产环境的灵活切换。

📅 今日工作总结 (2026.04.21)

1. 计划对比：阶段一 A/B 任务进度
任务 A (跨域污染自检) [超前完成]：今天通过引入 MD5 指纹账本 (manifest.json) 和 路径归一化 (as_posix)，从底层逻辑上彻底解决了文件识别模糊的问题。现在系统不仅能识别重名，还能根据内容指纹精准判断是否需要同步，为“边界感”验收打下了极稳的地基。

任务 B (负载与结构重构) [关键突破]：在准备多线程之前，先解决了最棘手的 “状态闭环” 问题。

缓存单例化：实现了 _CACHED_VECTORSTORE 全局缓存，这是后续实现“计算分流”的前提。

逻辑出口加固：修复了函数在无需重塑时返回 None 的 Bug。

2. 今日核心改动 (源码复盘)
[修正] 作用域冲突：将 FAISS 导入移至顶层，消除了函数内局部引用的隐患。

[增强] 审计闭环：在 save_local 后强制同步 save_manifest，确保“账实相符”，解决了连续点击按钮逻辑不重置的问题。

[优化] 交互反馈：在 st.rerun() 前强制加入微小延迟与缓冲区刷新，初步尝试解决 app_ui.py 加载动画与后端输出不同步的问题。

**核心成果：为下阶段“压力测试”扫清障碍**

今天关键加固：

指纹审计原子化：现在的 manifest.json 能精准区分“物理存在”与“逻辑记录”，这是搞 “50MB 级大数据量处理” 的安全底线。

内存单例实装：通过修复全局变量 _CACHED_VECTORSTORE 的更新逻辑，真正实现了“单例模式锁定”，显存溢出的风险在逻辑层被彻底堵死。

交互逻辑对齐：摸清了 Streamlit st.rerun 与后端 print 的缓冲冲突，为阶段二的“流式动画微调”积累了调试经验。

3. 🚩 源码提交点 (Commit Message)
fix(ingest): 完善指纹审计闭环与环境兼容性

- 路径处理：全量引入 as_posix()，消除 Windows/Linux 指纹比对差异。
- 逻辑修正：补全 initialize_knowledge_base 函数在“无需重塑”分支下的返回路径。
- 作用域修复：将 FAISS 导入提升至模块顶层，解决局部变量引用报错。
- 审计同步：调整 save_manifest 触发时机，确保数据库与账本状态物理一致。

📝 今日工作总结 (2026-04-22)
项目： 保险 AI 助手 (RAG)
核心任务： 知识库初始化流程重构与稳定性加固

1. 核心功能实现 (Core Improvements)
[指纹自省系统]：引入基于 MD5 的 manifest.json 机制。系统现在能够精准识别文件的 新增 (Added)、修改 (Changed) 和 删除 (Removed)，彻底解决了因文件修改时间（mtime）变动导致的误报。

[双模启动决策]：

热加载秒开：内容无差异时，毫秒级跳过解析，直接加载内存单例。

智能同步：仅在用户点击同步且侦测到差异时，才触发知识重塑。

[负载感知流控]：在向量化环节注入 Token 预算检查。当批次 Token 超过安全阈值（11,000）时自动执行保护性降速（休眠 2s），有效规避了大规模文档（如 1032 chunks）入库时 Ollama 的连接崩溃（10054 错误）。

2. 代码架构优化 (Architectural Refactoring)
[单例化治理]：

将 RecursiveCharacterTextSplitter 移出原子函数变为全局单例，减少了多线程并发时的对象创建开销。

实现了 _CACHED_VECTORSTORE 内存单例，并使用线程锁（Lock）确保 Streamlit 环境下的加载安全。

[解析引擎并发化]：ingest.py 升级为 12 线程并发模式，实测 1000+ 切片的读取与预处理在秒级完成。

3. 问题修复 (Bug Fixes)
[日志脱重]：清理了 ingest.py 与 ingest_service.py 之间的嵌套打印，解决了控制台“复读机”现象。

[编码鲁棒性]：加固了文本读取逻辑，针对特殊编码文件（如《沉沦》）实现了 latin-1 降级读取，确保 Pipeline 不因单文件解析失败而中断。

Git 提交建议

Commit Message 模板：
feat: 完善RAG知识库指纹自省系统与负载保护机制

1. 实现基于MD5的文件变动监控与manifest持久化
2. 优化initialize_knowledge_base逻辑，实现差异化“秒开”
3. 增加Token负载感知保护，解决大规模数据入库时的Ollama崩溃问题
4. 重构ingest引擎，单例化切片器并提升并发效率


🚀 Matrix Intelligence: Week Ending Summary (2026-04-24)
1. 已完成的底層架構 (Completed Infrastructure)
   12線程併發優化：成功壓榨 8 核 CPU 性能，設置 MAX_WORKERS=12，實現 I/O 與計算的極限平衡。
   MD5 全生命週期管理 (指紋閉環)：
       實現「新增-跳過-刪除」的自動同步邏輯。
       確保數據庫指紋與物理文件 1:1 對齊，避免孤兒索引。
   本地環境對齊：統一使用 .venv 虛擬環境與 PyCharm 映射路徑，修正 streamlit run 啟動路徑問題。
2. 核心邏輯與 UI 創新 (Logic & UX Innovation)
   置信區間 (Confidence Threshold)：
       實裝 $L2$ 距離到百分比的轉換公式：$Score = \max(0, 1 - \frac{d}{1.5}) \times 100\%$。
       產品哲學：引入「判斷權交還用戶」機制，提供「嚴謹/分析/探索」三檔模式，有效隔離 LLM 幻覺。
   
3. 下週工作計劃 (Next Week: Hybrid Search)
   目標：引入 BM25 + 向量 的混合檢索（Hybrid Search）。
   核心挑戰：RRF 融合算法調優、BM25 索引持久化、UI 滑動條與權重（Alpha）的動態關聯。
   技術債：準備從 SQLite 遷移至 Supabase (feat-supabase 分支)。

💾 Git 操作清單 (Checkout & Push)
### 1. 檢查狀態
git status

### 2. 暫存變更
git add .

### 3. 提交（使用我們總結的精簡版標題）
git commit -m "feat: implement 12-thread concurrency, MD5 fingerprint loop & confidence threshold logic"

### 4. 推送到開發分支
git push origin dev

 

---

### 📅 Matrix M3 階段工作計劃：RRF 融合檢索實裝

#### 第一階段：檢索器（Retriever）的最小化注入
* **任務**：在 `search_service.py` 中新增一個 `BM25Retriever` 類（或方法），負責從上週生成的 `bm25.pkl` 中讀取數據。
* **比對點**：確認 `.pkl` 文件路徑是否正確加載，以及 `jieba` 分詞是否與 Ingest 階段保持一致。

#### 第二階段：RRF (Reciprocal Rank Fusion) 算法實裝
* **任務**：編寫核心融合邏輯。這個算法不涉及複雜數學，它只是一個「排位賽」公式。
    * 公式原理：$Score = \sum_{d \in D} \frac{1}{k + r(d)}$
* **比對點**：檢查在相同提問下，向量路徑與關鍵字路徑分別返回的 Top 5 是否能正確合併。

#### 第三階段：主查詢入口重構與測試
* **任務**：修改 `ask` 或 `query` 主函數，將原本單一的 `vector_search` 替換為 `hybrid_search`。
* **比對點**：使用你上週提到的「條款編號」或「生僻術語」進行壓力測試，肉眼觀察「聰明程度」的提升。

---
📝## 📝 2026-04-30 代码审阅完成

### 已完成审阅的核心文件（18个）

| 序号 | 文件 | 状态 |
|------|------|------|
| 1 | .env | ✅ |
| 2 | requirements.txt | ✅ |
| 3 | app/config.py | ✅ |
| 4 | app/core/exceptions.py | ✅ |
| 5 | app/core/logger.py | ✅ |
| 6 | app/core/engine.py | ✅ |
| 7 | app/models/embeddings.py | ✅ |
| 8 | app/models/llm.py | ✅ |
| 9 | app/storage/vector_db.py | ✅ |
| 10 | app/pipeline/loader.py | ✅ |
| 11 | app/pipeline/ingest.py | ✅ |
| 12 | app/pipeline/watcher.py | ✅ |
| 13 | app/services/ingest_service.py | ✅ |
| 14 | app/services/watcher_service.py | ✅ |
| 15 | app/services/search_service.py | ✅ |
| 16 | app/utils/hash_utils.py | ✅ |
| 17 | app_ui.py | ✅ |
| 18 | main.py | ✅ |

### 主要成果

- 统一异常脱水平台 (exceptions.py)
- 混合检索引擎 (FAISS + BM25 + RRF)
- 完善哨兵监控与服务层架构
- 修复配置文件路径计算逻辑
- Streamlit UI 冷热启动拦截器

### 核心修改摘要

1. config.py: 新增 LOG_LEVEL 配置，完善路径自动计算
2. logger.py: 支持从配置文件读取日志级别
3. search_service.py: BM25 路径统一使用 settings，doc_id 改为 MD5 哈希
4. watcher.py: 保留独立运行入口，哨兵仅记录变动不自动入库
5. ingest_service.py: 删除 load_dotenv()，统一使用 settings
6. main.py: 新增 --reindex 参数，支持 CLI 域过滤查询


早！很高興聽到項目初步搭建完成。以下是基於我們之前的協作記錄整理的 **上周工作總結**、**完成度對比** 和 **本周計劃**。

---

## 📊 一、上周工作總結 (2026.04.28 - 2026.05.04)

### 1. 核心架構落地

| 模塊 | 成果 |
|------|------|
| **配置層** | `config.py` 完成 Pydantic Settings 單例化，支援 `.env` 動態覆蓋 |
| **異常脫水平台** | `exceptions.py` 統一異常處理，解決生成器 NameError 問題 |
| **日誌系統** | `logger.py` 支援 `LOG_LEVEL` 配置，整合全局日誌輸出 |
| **向量存儲** | `vector_db.py` 完成 FAISS + SQLite 聯合存儲架構 |
| **混合檢索** | `search_service.py` 實現 FAISS + BM25 + RRF 融合檢索 |
| **流水線層** | `loader.py` + `ingest.py` 支援 PDF/Word/TXT 解析與切片 |
| **服務層** | `ingest_service.py` + `watcher_service.py` 實現多線程併發與哨兵監控 |
| **UI 層** | `app_ui.py` 完成冷熱啟動攔截器、資產審計看板、認知溯源卡 |
| **CLI 入口** | `main.py` 支援 `--reindex` 參數與域過濾查詢 |

### 2. 核心安全規範落地

| 規範 | 狀態 | 實現位置 |
|------|------|----------|
| 異常脫水協議 | ✅ | `exceptions.py` + 生成器中的 `dehydrate_exception` |
| 物理域隔離 | ✅ | `engine.py` 強制 `filter_domain` 過濾 |
| 分批吞吐限流 | ✅ | `INGEST_BATCH_SIZE` + Token 預算檢查 |
| 冷熱隔離攔截 | ✅ | `app_ui.py` 啟動時檢查索引是否存在 |
| 單例模式鎖定 | ✅ | `_CACHED_VECTORSTORE` + 執行緒鎖 |

### 3. 技術債清理

- [x] 路徑計算統一使用 `BASE_DIR` 絕對路徑
- [x] 移除 `load_dotenv()` 重複加載
- [x] `search_service.py` 中 `doc_id` 改為 MD5 哈希（避免隱私洩漏）
- [x] `watcher.py` 保留獨立運行入口，哨兵僅記錄不自動入庫
- [x] `logger.py` 支援從配置讀取日誌級別

---

## 📈 二、項目完成度對比

### 整體進度

| 階段 | 計劃 | 完成 | 完成度 |
|------|------|------|--------|
| 架構設計 | 五層架構方案 | ✅ 全部確認 | 100% |
| 核心安全規範 | 5 項契約 | ✅ 全部落地 | 100% |
| 配置層 | `config.py` + `.env` | ✅ | 100% |
| 模型層 | `llm.py` + `embeddings.py` | ✅ | 100% |
| 存儲層 | `vector_db.py` | ✅ | 100% |
| 流水線層 | `loader.py` + `ingest.py` + `watcher.py` | ✅ | 100% |
| 服務層 | `ingest_service.py` + `watcher_service.py` + `search_service.py` | ✅ | 100% |
| 內核層 | `engine.py` | ✅ | 100% |
| UI 層 | `app_ui.py` | ✅ | 100% |
| CLI 入口 | `main.py` | ✅ | 100% |
| 指紋系統 | `hash_utils.py` + `manifest.json` | ✅ | 100% |
| 混合檢索 | RRF 融合引擎 | ✅ | 100% |

### 待完成/待優化項

| 任務 | 狀態 | 優先級 |
|------|------|--------|
| 清理 UI 調試代碼（`st.write`） | ⏳ 待處理 | 低 |
| 新增域自動創建文件夾 | ⏳ 待處理 | 中 |
| API 接口（FastAPI） | ⏳ 未開始 | 中 |
| 智能建議（後續問題推薦） | ⏳ 未開始 | 低 |
| Session 狀態持久化 | ⏳ 未開始 | 中 |
| RBAC 身份識別 | 📅 Phase 2 | 低 |

---

## 📅 三、本周計劃 (2026.05.05 - 2026.05.09)

### 階段一：穩定性驗證與壓力測試 (Day 1-2)

| 任務 | 說明 | 驗收標準 |
|------|------|----------|
| 跨域污染測試 | 不同 Domain 存放同名文件，驗證過濾邏輯 | 財務域看不到行政域文件 |
| 大文件壓力測試 | 上傳 50MB+ PDF，觀察系統響應 | 不崩潰，不 OOM |
| 併發上傳測試 | 同時上傳 20+ 文件 | 哨兵正確觸發，無漏檢 |
| 指紋一致性檢查 | 修改文件後重複同步 | manifest 與物理文件一致 |

### 階段二：用戶體驗優化 (Day 3-4)

| 任務 | 說明 | 驗收標準 |
|------|------|----------|
| 溯源卡片增強 | 顯示匹配得分、來源文件名、預覽片段 | UI 正確渲染得分與預覽 |
| 同步進度條 | 全量索引審計時顯示進度 | 用戶可感知進度 |
| 清理調試代碼 | 移除 `st.write`、`print` 等 | 控制台乾淨 |
| 新增域自動創建 | UI 新增域時自動創建物理文件夾 | 無需手動創建目錄 |

### 階段三：API 接口預研 (Day 5)

| 任務 | 說明 | 驗收標準 |
|------|------|----------|
| FastAPI 基礎搭建 | 創建 `app/api/` 目錄結構 | 服務可啟動 |
| `/query` 接口 | 支援 POST 請求，返回 RAG 結果 | 與 UI 行為一致 |
| `/ingest` 接口 | 支援文件上傳與知識入庫 | 同步觸發流水線 |

---

## 🚩 本週里程碑交付物

- [ ] **壓力測試報告**：記錄 50MB+ 文件的處理耗時與資源佔用
- [ ] **溯源增強版 UI**：得分顯示 + 預覽片段 + 來源文件
- [ ] **API 接口原型**：`/query` 和 `/ingest` 基礎版本

---
【核心變更說明】2026-05-07

數據持久化層 (Safe-Storage)：

實裝 portalocker 進程鎖與線程鎖，解決多進程併發寫入衝突。

引入「臨時寫入-原子替換」機制，徹底杜絕斷電或崩潰導致的索引損壞 (0KB 隱患)。

增加自動備份邏輯，在重塑索引前對舊庫進行時間戳備份。

跨平台路徑歸一化 (Path Normalization)：

全量遷移至 pathlib.Path，強制使用 .as_posix() (正斜槓)。

解決 Windows/Linux 環境下因路徑分隔符不一致導致的資產指紋失效問題。

解析引擎升級 (Ingest Refactor)：

重構為 process_file_to_docs 單一入口。

夯實編碼探測邏輯，精確捕獲 UnicodeDecodeError，消除「沉默失敗」。

修復 PyCharm 類型檢查警告，提升代碼靜態安全性。

監控哨兵優化 (Watcher Robustness)：

增加 get_source_manifest 的目錄存在性檢查，防止系統冷啟動崩潰。

優化導入路徑與 sys.path 適配，支持「模塊運行」與「腳本運行」雙模式。


2026-05-14 by Gemini
1.斷點續傳：在 ingest.py 中增加針對超大型 PDF 的切片保存機制。

2.監控自愈：當 watcher_service.py 檢測到物理目錄丟失時，自動調用 domain_service.py 進行補全。

3.併發優化：在 rerank_service.py 中引入 Batch 處理，提升多片段重排的效率。


📝 項目更新日誌 (Git Commit Summary)2026-05-15
🚀 核心優化：RAG 性能與內存管理調優
1. 檢索層 (Search Service) - 從「IO 密集」轉向「內存駐留」
單例緩存 (Singleton Pattern)：引入全局靜態變量 _global_vectorstore 與 _global_bm25_data，實現索引文件的一次加載，永久復用。徹底消滅了每次檢索時 1.3s 的磁盤讀取開銷。

懶加載鎖定：優化 _load_indices 邏輯，增加內存攔截。日誌證實熱加載後檢索耗時從 1300ms 降至 100ms 級別。

2. 模型層 (LLM Engine) - 實現「零冷啟動」常駐
內存駐留策略：配置 keep_alive="24h"，配合系統內存清理，確保模型權重鎖定在 RAM 中，避免 Windows 分頁交換導致的 20s+ 延遲。

計算負荷優化：將 top_k 調整為 1，在保證核心知識召回的前提下，將 CPU 的預填充（Pre-fill）負荷降至最低。

參數對齊：統一 num_ctx 指令窗口，優化 KV Cache 命中率，實現相同话题下的 1.6s 極速回顯。

3. 基礎設施與監控 (Monitoring)
指標可視化：完善 METRICS 日誌輸出，新增 REAL_TTFT（真實首字響應）與 v_ms / b_ms 拆解，便於精確定位性能瓶頸。

資源競爭緩解：建議並實施了「環境脫水」，通過釋放系統無效內存，提升了 CPU 推理時的帶寬優先級。