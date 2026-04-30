# app/services/ingest_service.py
import os
import json
import time
import threading # 新增：用于线程锁
import tiktoken  # 用于精准 Token 预算
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Tuple
# from app.services.watcher_service import start_sentinel # 從watcher引入哨兵

# 引入Hybrid
import pickle
import jieba
from rank_bm25 import BM25Okapi

#  【必须先加载环境】
# from dotenv import load_dotenv
# load_dotenv() # 必须在所有 getenv 之前运行！

from app.config import settings
from app.core.logger import logger
from langchain_community.vectorstores import FAISS
from app.models.embeddings import embeddings
from langchain_core.documents import Document

# 【变量归位】哨兵和增量逻辑公用的“地图”
# 这里直接从环境变量拿，确保全局可见
DATA_UPLOAD_DIR = settings.DATA_UPLOAD_DIR
VECTOR_DB_DIR = settings.VECTOR_DB_DIR

# 新增：BM25 專屬目錄路徑，精準對齊你手建的 data/bm25_db
# 統一來自config定義 BM25_DB_DIR = os.path.join("data", "bm25_db")
BM25_PKL_PATH = os.path.join(settings.BM25_DB_DIR, "bm25.pkl")

# 导入新增的指纹工具与扫描逻辑
from app.pipeline.watcher import get_source_manifest

# ------------- 全局配置变量 ----------------------
# 设定 MAX_WORKERS 的设计逻辑：统一并发阈值：取核心数+4与12的最小值
MAX_WORKERS = min(12, (os.cpu_count() or 1) + 4)

# 单次 Embedding 批次上限设计逻辑：2000-4000 token 是吞吐量最优区间
BATCH_TOKEN_LIMIT = 3000

# [架构级锁定]：全局单例变量
# 作用：根治 Streamlit 环境下因多次初始化导致的日志重复和内存浪费
# [架构级锁定原因记录]：
# Streamlit 采用“自顶向下”的刷新机制，每次 UI 交互都会重跑整个脚本。
# 1. _CACHED_VECTORSTORE 设为全局单例，避免重复从磁盘加载几百 MB 的索引造成内存溢出。
# 2. _DB_RW_LOCK  互斥锁确保在多线程环境下（如增量更新时）对向量库的写入是线程安全的。
# 3. 哨兵启动必须检查线程池状态，否则每次页面刷新都会新建一个死循环线程，导致 CPU 炸裂和日志刷屏。
_CACHED_VECTORSTORE = None  # 内存单例：确保整个应用生命周期只维护一个向量库对象
_CACHED_BM25 = None  # 新增：BM25 內存單例，減少磁盤 IO
_DB_RW_LOCK = threading.Lock()  # 互斥锁：防止多线程环境下对向量库的读写冲突，确保单例赋值时的线程安全


# 【状态协议】：指纹快照存储路径，位于向量库同级目录
db_path = settings.VECTOR_DB_DIR  # 统一使用这个变量
MANIFEST_FILE = os.path.join(db_path, "manifest.json")

# ------------- 全局配置变量结束 ----------------------

# 初始化 Token 计数器
try:
    _ENCODER = tiktoken.get_encoding("cl100k_base")
except:
    _ENCODER = tiktoken.get_encoding("gpt2")

# token计算
def get_token_count(text: str) -> int:
    """计算字符串的精确 Token 数量"""
    return len(_ENCODER.encode(text))


# ------------- [新增] BM25 持久化邏輯 --------------------------
def _save_bm25_index(documents: List[Document]):
    """
    【重要架構說明】：向量庫可以增量添加，但 BM25 依賴全局 TF-IDF 統計。
    為了保證搜索精度，目前採取『全量重構 BM25』策略。
    """
    if not documents:
        logger.warning("⚠️ [Hybrid] 無有效文檔，跳過 BM25 重構")
        return
    try:
        os.makedirs(settings.BM25_DB_DIR, exist_ok=True)

        # --- 健壮性分词逻辑 ---
        tokenized_corpus = []
        # 强制检查 jieba 是否真的加载了 lcut
        use_jieba = hasattr(jieba, 'lcut_for_search')

        for doc in documents:
            if use_jieba:
                tokens = jieba.lcut_for_search(doc.page_content)
            else:
                # 极端降级：如果 jieba 彻底崩了，按空格分詞，保證程序不掛
                tokens = doc.page_content.split()
            tokenized_corpus.append(tokens)

        # --- 变量定义对齐 ---
        bm25_instance = BM25Okapi(tokenized_corpus)

        if bm25_instance:
            hybrid_data = {
                "instance": bm25_instance,
                "documents": documents
            }

            # 确保目录存在
            with open(BM25_PKL_PATH, "wb") as f:
                pickle.dump(hybrid_data, f)
            logger.info(f"💾 [Hybrid] BM25 索引已固化至: {BM25_PKL_PATH}")
        else:
            logger.error("❌ [Hybrid] BM25 實例化失敗，放棄持久化")
    except Exception as e:
        # 捕获所有异常，防止增量同步因 Hybrid 插件失败而回滾
        logger.error(f"❌ [Hybrid] BM25 構建失敗 (環境異常): {str(e)}")

# -------------指纹读写--------------------------
def get_saved_manifest() -> Dict[str, str]: # noqa: W0212
    """读取上一次成功索引时的文件指纹快照"""
    if os.path.exists(MANIFEST_FILE):
        try:
            with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"⚠️ [快照损坏] 无法读取指纹清单: {e}")
    return {}
# -----------------持久化指纹----------------------------
def save_manifest(manifest: Dict[str, str]): # noqa: W0212
    """持久化当前文件指纹快照"""
    try:
        os.makedirs(os.path.dirname(MANIFEST_FILE), exist_ok=True)
        with open(MANIFEST_FILE, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
        logger.info("💾 [快照归档] 指纹清单已物理固化。")
    except Exception as e:
        logger.error(f"❌ [IO错误] 无法保存指纹清单: {e}")

# *******专用检查工具函数，发现MD5是否一致***********
def _get_manifest_diff() -> Tuple[Dict[str, str], int, bool]: # noqa: W0212
    """[自省层] 差异分析逻辑抽象，返回 (当前指纹, 差异总数, 是否存在差异)"""
    current_manifest = get_source_manifest(settings.DATA_UPLOAD_DIR)
    saved_manifest = get_saved_manifest()

    added = [f for f in current_manifest if f not in saved_manifest]
    removed = [f for f in saved_manifest if f not in current_manifest]
    changed = [f for f in current_manifest if f in saved_manifest and current_manifest[f] != saved_manifest[f]]

    total_diff = len(added) + len(removed) + len(changed)
    return current_manifest, total_diff, total_diff > 0

# 切片入库
def _handle_rebuild_logic(documents: List[Document], current_manifest: Dict[str, str]) -> FAISS: # noqa: W0212
    logger.info(f"📊 [负载感知] 待处理切片: {len(documents)}，批次规模: {settings.INGEST_BATCH_SIZE}")
    vectorstore = None
    start_time = time.time()

    for i in range(0, len(documents), settings.INGEST_BATCH_SIZE):
        batch = documents[i: i + settings.INGEST_BATCH_SIZE]
        # --- [緊急除錯注入] ---
        if i == 0:
            logger.info(f"🔍 [數據採樣] 樣本來源: {batch[0].metadata.get('source')}")
            logger.info(f"🔍 [數據採樣] 樣本內容預覽: {batch[0].page_content[:100]}")
        # ----------------------

        # --- [保留用戶原始源碼：Token 负载感知] ---
        # 這裡恢復你原有的強類型訪問，不擅自改動為 .get()
        batch_tokens = sum(doc.metadata["token_count"] for doc in batch)
        if batch_tokens > 6000:
            logger.warning(f"⚠️ [负载预警] 当前批次 Token ({batch_tokens}) 过高，即将触发降速处理...")
        if batch_tokens > 11000:
            logger.warning(f"⚠️ [负载过高] 正在进行保护性降速...")
            time.sleep(2)

        if vectorstore is None:
            vectorstore = FAISS.from_documents(batch, embeddings)
        else:
            vectorstore.add_documents(batch)

        if (i // settings.INGEST_BATCH_SIZE) % 5 == 0 or (i + len(batch) >= len(documents)):
            logger.info(f"🚀 [计算中] 向量化进度: {(i + len(batch)) / len(documents) * 100:.1f}%")

    # --- [Hybrid 注入] ---
    if vectorstore:
        _save_bm25_index(documents) # 同步構建關鍵字索引
        os.makedirs(db_path, exist_ok=True)
        vectorstore.save_local(db_path)
        save_manifest(current_manifest)

        duration = time.time() - start_time
        logger.info(f"✅ [重塑成功] 耗时: {duration:.2f}s | 状态: 索引与指纹已双向锁定。")

    return vectorstore

# 负责多线程解析
def _parallel_load_and_split() -> List[Document]:
    # 刪除 logger.info(f"💾 [磁盤讀取] 開始物理掃描: {full_path} | 大小: {os.path.getsize(full_path) / 1024:.2f} KB")
    """并发解析引擎，执行原子化解析与 Token 预计算"""
    from app.pipeline.ingest import list_all_files, process_file_to_docs
    files = list_all_files(settings.DATA_UPLOAD_DIR)
    all_docs = []

    if not files:
        logger.warning("📂 数据目录中未发现可处理的文件。")
        return all_docs

    logger.info(f"⚡ [并发引擎] 启动 {MAX_WORKERS} 线程并行解析...")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # 原子任务分发至线程池
        future_to_file = {executor.submit(process_file_to_docs, f): f for f in files}

        for future in as_completed(future_to_file):
            file_name = future_to_file[future]
            try:
                docs = future.result()
                if docs:
                    # 【核心注入】：在解析阶段就锁定 Token 数，为后续分批做依据
                    for doc in docs:
                        doc.metadata["token_count"] = get_token_count(doc.page_content)
                    all_docs.extend(docs)
            except Exception as e:
                logger.error(f"❌ [原子失效] 文件 {file_name} 解析崩溃: {e}")

    return all_docs
# ==========================================
# 2. 增量执行函数 (Incremental - 物理差量层)
# ==========================================

def _execute_incremental_sync(current_manifest):
    """
    【设计依据 - 物理差量层】
    1. 核心：仅对 Added/Changed 名单进行解析，并执行向量库物理剔除。
    2. [M3 核心注入]：增量更新后，必须重构 BM25 索引以保持全局 TF-IDF 准确性。
    """
    global _CACHED_VECTORSTORE
    print(f"\n========================= 🔄 [场景2: 增量同步更新] =========================")


    try:
        from app.pipeline.ingest import process_file_to_docs
        start_time = time.time()

        # 1. 提取变动名单 (对齐你的源码变量名)
        saved_manifest = get_saved_manifest()
        added_or_changed = [f for f, md5 in current_manifest.items() if saved_manifest.get(f) != md5]
        deleted_files = [f for f in saved_manifest.keys() if f not in current_manifest]

        if not added_or_changed and not deleted_files:
            logger.info("📡 [增量中止] 检测到指纹一致，无须执行物理更新。")
            return _CACHED_VECTORSTORE

        logger.info(f"🎯 [增量决策] 识别到变动: 增/改 {len(added_or_changed)} | 删除 {len(deleted_files)}")

        # 2. 状态感知：确保加载基础索引
        if _CACHED_VECTORSTORE is None:
            index_path = os.path.join(db_path, "index.faiss")
            if os.path.exists(index_path):
                logger.info("📂 [单例挂载] 正在加载现有索引...")
                _CACHED_VECTORSTORE = FAISS.load_local(db_path, embeddings, allow_dangerous_deserialization=True)
            else:
                logger.warning("⚠️ [索引缺失] 磁盘未发现 index.faiss，降级为全量重塑。")
                return _execute_full_rebuild(current_manifest)

        # 3. 【解析层】局部解析
        incremental_docs = []
        for idx, file_path in enumerate(added_or_changed):
            # --- [核心修復点：路徑補全] ---
            # 確保 file_path 加上 settings.DATA_UPLOAD_DIR，防止 os.path.exists(0.05s) 空轉問題
            full_path = file_path if os.path.isabs(file_path) else os.path.join(settings.DATA_UPLOAD_DIR, file_path)

            if not os.path.exists(full_path):
                logger.error(f"❌ [路径失效] 找不到资产: {full_path}")
                continue

            # --- [正確位置] 注入磁盤讀取日誌 ---
            file_size = os.path.getsize(full_path) / 1024
            logger.info(f"💾 [磁盤讀取] 掃描目標: {os.path.basename(full_path)} | 大小: {file_size:.2f} KB")

            logger.info(f"🔄 [解析中] ({idx + 1}/{len(added_or_changed)}) -> {os.path.basename(full_path)}")
            docs = process_file_to_docs(full_path)
            if docs:
                for d in docs:
                    d.metadata["token_count"] = get_token_count(d.page_content)
                    d.metadata["source"] = os.path.basename(full_path)
                    # 确保 domain 写入 (如果你按目录分域)
                    rel_path = os.path.relpath(os.path.dirname(full_path), settings.DATA_UPLOAD_DIR)
                    d.metadata["domain"] = rel_path if rel_path != "." else "未分类资产"
                incremental_docs.extend(docs)

        # 4. 【执行层】物理写库 (加锁)
        with _DB_RW_LOCK:
            write_start = time.time()

            # --- 动作 A: 处理移除 ---
            if deleted_files:
                for f in deleted_files:
                    # 必須與 ingest.py 中的歸一化邏輯 100% 一致
                    target_key = os.path.basename(f)

                    ids_to_delete = [
                        k for k, doc in _CACHED_VECTORSTORE.docstore._dict.items() # noqa: W0212
                        if doc.metadata.get("source") == target_key
                    ]
                    if ids_to_delete:
                        _CACHED_VECTORSTORE.delete(ids=ids_to_delete)
                        logger.info(f"🗑️ [清理完成] 已物理剔除 ID 數量: {len(ids_to_delete)} ({os.path.basename(f)})")
                    else:
                        logger.warning(f"⚠️ [清理跳過] 索引中未找到文件標籤: {target_key}")
            # --- 动作 B: 处理新增/修改 ---
            if incremental_docs:
                _CACHED_VECTORSTORE.add_documents(incremental_docs)
                logger.info(f"📊 [追加完成] 累计写入 {len(incremental_docs)} 个新切片")

            # --- [M3 核心注入]：重构 BM25 ---
            # 无论增删，只要变动，就从当前向量库提取全量 Document 重構 BM25
            all_docs = list(_CACHED_VECTORSTORE.docstore._dict.values()) # noqa: W0212
            _save_bm25_index(all_docs)

            # 5. 【固化层】
            logger.info(f"💾 [磁盤寫入] 正在固化 FAISS 索引至: {db_path}")
            _CACHED_VECTORSTORE.save_local(db_path)
            save_manifest(current_manifest) # 只有成功走到这里，才存指纹

            write_duration = time.time() - write_start
            logger.info(f"💾 [固化成功] 磁盤 IO 耗時: {write_duration:.2f}s")

            # --- [最終校驗] ---
            idx_file = os.path.join(db_path, "index.faiss")
            if os.path.exists(idx_file):
                logger.info(f"📈 [物理變動] index.faiss 最終大小: {os.path.getsize(idx_file) / 1024:.2f} KB")

        total_duration = time.time() - start_time
        logger.info(f"✅ [同步成功] 总耗時: {total_duration:.2f}s | 状态：向量库与 BM25 已锁定。")
        return _CACHED_VECTORSTORE

    except Exception as e:
        logger.error(f"🚨 [增量失效] 发生不可预知错误: {str(e)}", exc_info=True)
        raise e

# ==========================================
# 3. 全量同步 (物理覆盖)
# ==========================================
def _execute_full_rebuild(current_manifest):
    """
    彻底清空并重新构建所有索引。
    """
    global _CACHED_VECTORSTORE
    import shutil  # 確保導入
    print(f"\n========================= 🚀 [场景3: 全量重塑] =========================")
    try:
        # from app.services.ingest_service import _parallel_load_and_split
        # 这里的函数是扫描全量目录的
        # --- [新增：物理清空防止體積膨脹] ---
        if os.path.exists(db_path):
            shutil.rmtree(db_path)
            logger.warning(f"🧹 [物理清空] 已刪除舊向量庫目錄: {db_path}")
        os.makedirs(db_path, exist_ok=True)

        # 重置內存單例
        _CACHED_VECTORSTORE = None
        # ----------------------------------

        # 重新併發解析所有文件
        all_docs = _parallel_load_and_split()
        if not all_docs:
            logger.warning("📂 未發現任何文檔，全量重塑終止")
            return None

        # 調用底層入庫邏輯
        new_vs = _handle_rebuild_logic(all_docs, current_manifest)

        with _DB_RW_LOCK:
            _CACHED_VECTORSTORE = new_vs
        return _CACHED_VECTORSTORE
    except Exception as e:
        logger.error(f"🚨 [全量失败] {e}")
        raise e


# ==========================================
# 4. 主入口分流 (Dispatcher - 逻辑指挥部)
# ==========================================
def initialize_knowledge_base(force_rebuild=False, check_manifest=True):
    """
    【RAG 核心調度指揮部 - 扁平化原子決策引擎】
    """
    global _CACHED_VECTORSTORE

    # 1. 狀態感知：獲取磁盤最新指紋與歷史快照
    current_manifest, diff_count, has_diff = _get_manifest_diff()
    index_exists = os.path.exists(os.path.join(db_path, "index.faiss"))

    # 2. 決策分流 (Dispatcher Logic)
    # --- [場景 1: 強制全量重塑] ---
    if force_rebuild:
        _CACHED_VECTORSTORE = _execute_full_rebuild(current_manifest)

    # --- [場景 2: 增量同步更新] ---
    # 觸發條件：(索引不存在) 或 (有變動 且 開啟了檢查)
    elif not index_exists or (has_diff and check_manifest):
        # 注意：save_manifest 被移入 _execute_incremental_sync 內部，
        # 確保「解析 -> 向量化 -> BM25 -> 固化」全部成功後才更新指紋。
        _CACHED_VECTORSTORE = _execute_incremental_sync(current_manifest)

    # --- [場景 3: 靜默啟動/資產一致] ---
    else:
        print(f"\n————————————————————————— 🎯 [場景 3: 資產狀態一致] —————————————————————————")
        logger.info("📡 [自檢回響] 本地資產與索引指紋 100% 吻合，執行熱加載。")

        # 僅在內存為空時加載，避免重複讀取磁盤
        if _CACHED_VECTORSTORE is None and index_exists:
            with _DB_RW_LOCK:
                _CACHED_VECTORSTORE = FAISS.load_local(
                    db_path,
                    embeddings,
                    allow_dangerous_deserialization=True
                )

    # 3. 邏輯閉環：激活實時監控哨兵
    from app.services.watcher_service import start_sentinel
    start_sentinel()

    return _CACHED_VECTORSTORE

    # [辅助逻辑注释：去抖动策略]
    # 在 start_sentinel 的 while True 循环中必须包含 time.sleep(0.5)。
    # 原因：合并操作系统高频产生的 IO 修改事件信号（去抖 Debounce），
    # 确保 has_diff 的判断发生在文件写入完成后的稳定状态。