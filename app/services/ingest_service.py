# app/services/ingest_service.py
import os
import json
import time
import threading
import shutil
import tempfile
import glob
import pickle
import jieba
import portalocker
from pathlib import Path
from datetime import datetime
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Tuple, Optional

from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from rank_bm25 import BM25Okapi

from app.config import settings
from app.core.logger import logger
from app.models.embeddings import embeddings
from app.pipeline.watcher import get_source_manifest
from app.pipeline.ingest import list_all_files, process_file_to_docs

# ==========================================
# 核心單例與鎖：確保內存唯一與線程安全
# ==========================================
_CACHED_VECTORSTORE = None  # 向量庫內存單例，避免重複加載幾百MB的文件
_CACHED_BM25 = None  # BM25 內存單例
_DB_RW_LOCK = threading.Lock()  # 線程鎖，防止多個用戶同時點擊「重塑」導致內存崩潰

# ==========================================
# 鎖路徑定義：跨進程同步的「信標」
# ==========================================
INDEX_LOCK_DIR = settings.VECTOR_DB_DIR / ".process_lock"


@contextmanager
def cross_process_lock():
    """
    【防禦層】跨進程文件鎖
    原理：在操作系統臨時目錄創建一個鎖文件。
    作用：當你在 Streamlit 點擊刷新或多個進程啟動時，確保只有一個人在寫磁盤。
    """
    INDEX_LOCK_DIR.mkdir(parents=True, exist_ok=True)
    lock_file = INDEX_LOCK_DIR / "matrix_db.lock"
    with open(lock_file, "w") as f:
        try:
            # 嘗試獲取鎖（非阻塞）
            portalocker.lock(f, portalocker.LOCK_EX | portalocker.LOCK_NB)
            yield
        except portalocker.exceptions.LockException:
            # 如果鎖被佔用，則進入排隊等待
            logger.warning("⚠️ 檢測到其他進程正在寫入索引，請稍候...")
            portalocker.lock(f, portalocker.LOCK_EX)
            yield
        finally:
            portalocker.unlock(f)


# ==========================================
# BM25 邏輯：精確關鍵詞搜索的基層
# ==========================================
def _save_bm25_index(documents: List[Document]):
    """
    為什麼要重構：BM25 依賴全局詞頻統計。任何文件的增刪，
    都必須重新計算所有文檔的權重，才能保證關鍵詞搜索的準確性。
    """
    if not documents: return
    try:
        # 使用 jieba 的搜索模式進行分詞
        tokenized_corpus = [jieba.lcut_for_search(doc.page_content) for doc in documents]
        bm25_instance = BM25Okapi(tokenized_corpus)

        # 將實例與原始文檔封裝，方便後續 Hybrid 搜索調用
        hybrid_data = {"instance": bm25_instance, "documents": documents}

        bm25_path = Path(settings.BM25_DB_DIR) / "bm25.pkl"
        bm25_path.parent.mkdir(parents=True, exist_ok=True)
        with open(bm25_path, "wb") as f:
            pickle.dump(hybrid_data, f)

        # 同步更新內存緩存
        global _CACHED_BM25
        _CACHED_BM25 = hybrid_data
        logger.info(f"💾 [Hybrid] BM25 索引已成功重塑並固化")
    except Exception as e:
        logger.error(f"❌ [Hybrid] BM25 構建失敗 (環境異常): {e}")


# ==========================================
# 安全保存邏輯：物理層的三層防護
# ==========================================
def safe_save_vectorstore(vectorstore, db_path: Path):
    """
    【三層防護體系】
    1. 備份層：寫入前對舊數據進行時間戳備份。
    2. 臨時層：先在系統臨時目錄生成新文件，避免直接在正式目錄寫入時斷電。
    3. 原子層：利用 shutil.move 的原子特性一秒切換，確保磁盤索引永遠完整。
    """
    db_path.mkdir(parents=True, exist_ok=True)

    # --- 第1步：自動備份 ---
    if (db_path / "index.faiss").exists():
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = db_path.parent / f"vector_db_bak_{ts}"
        try:
            shutil.copytree(db_path, backup)
            logger.info(f"📦 [安全防護] 已創建歷史備份: {backup.name}")
        except:
            pass  # 備份失敗不阻斷主進程

    # --- 第2/3步：臨時寫入與原子替換 ---
    with tempfile.TemporaryDirectory() as tmpdir:
        vectorstore.save_local(tmpdir)
        with cross_process_lock():
            # 將臨時文件移動到正式路徑
            for item in os.listdir(tmpdir):
                shutil.move(os.path.join(tmpdir, item), db_path / item)
    logger.info(f"✅ [磁盤IO] 索引已物理固化至: {db_path}")


# ==========================================
# 同步邏輯：增量更新與全量重塑
# ==========================================
def _execute_incremental_sync(current_manifest):
    """
    【增量引擎】
    邏輯：讀取 manifest.json，找出 MD5 變化的文件。
    動作：刪除舊索引 -> 解析新文件 -> 追加新索引。
    """
    global _CACHED_VECTORSTORE
    saved_manifest = _get_saved_manifest()

    # 找出：新增/修改的文件，以及被刪除的文件
    added_or_changed = [f for f, md5 in current_manifest.items() if saved_manifest.get(f) != md5]
    deleted_files = [f for f in saved_manifest.keys() if f not in current_manifest]

    if not added_or_changed and not deleted_files:
        logger.info("📡 [靜默] 無資產變動，跳過增量更新。")
        return _CACHED_VECTORSTORE

    # 確保內存中有基礎向量庫
    if _CACHED_VECTORSTORE is None:
        if (settings.VECTOR_DB_DIR / "index.faiss").exists():
            _CACHED_VECTORSTORE = FAISS.load_local(str(settings.VECTOR_DB_DIR), embeddings,
                                                   allow_dangerous_deserialization=True)
        else:
            return _execute_full_rebuild(current_manifest)

    with _DB_RW_LOCK:
        # --- A. 物理剔除已刪除文件 ---
        if deleted_files:
            for f in deleted_files:
                target_key = f.replace('\\', '/')
                # 在 FAISS 字典中查找 source 標籤匹配的 ID
                ids = [k for k, d in _CACHED_VECTORSTORE.docstore._dict.items() if
                       d.metadata.get("source") == target_key]
                if ids:
                    _CACHED_VECTORSTORE.delete(ids=ids)
                    logger.info(f"🗑️ [清理] 已剔除失效資產: {f}")

        # --- B. 局部解析並追加新數據 ---
        if added_or_changed:
            new_docs = []
            for rel_f in added_or_changed:
                full_p = settings.DATA_UPLOAD_DIR / rel_f
                new_docs.extend(process_file_to_docs(str(full_p)))
            if new_docs:
                _CACHED_VECTORSTORE.add_documents(new_docs)
                logger.info(f"🚀 [追加] 已寫入 {len(new_docs)} 個新切片")

        # --- C. 同步更新 BM25 並固化 ---
        _save_bm25_index(list(_CACHED_VECTORSTORE.docstore._dict.values()))
        safe_save_vectorstore(_CACHED_VECTORSTORE, settings.VECTOR_DB_DIR)
        _save_manifest(current_manifest)

    return _CACHED_VECTORSTORE


def _execute_full_rebuild(current_manifest):
    """
    【重塑引擎】
    當你手動點擊「強制重塑」或索引損壞時觸發。
    動作：清空目錄 -> 重新併發解析 -> 重新生成所有索引。
    """
    global _CACHED_VECTORSTORE
    logger.warning("🔥 [警告] 正在啟動全量重塑，這將重建所有索引...")

    if settings.VECTOR_DB_DIR.exists():
        shutil.rmtree(settings.VECTOR_DB_DIR)

    # 併發解析所有文件
    files = list_all_files(str(settings.DATA_UPLOAD_DIR))
    all_docs = []
    with ThreadPoolExecutor(max_workers=settings.INGEST_MAX_WORKERS) as pool:
        futures = {pool.submit(process_file_to_docs, f): f for f in files}
        for fut in as_completed(futures):
            all_docs.extend(fut.result())

    if all_docs:
        # 從零構建 FAISS
        new_vs = FAISS.from_documents(all_docs, embeddings)
        _save_bm25_index(all_docs)
        safe_save_vectorstore(new_vs, settings.VECTOR_DB_DIR)
        _save_manifest(current_manifest)
        with _DB_RW_LOCK:
            _CACHED_VECTORSTORE = new_vs
    return _CACHED_VECTORSTORE


# ==========================================
# 主入口：知識庫自動初始化
# ==========================================
def initialize_knowledge_base(force_rebuild=False):
    """
    【矩陣指揮部】
    決策鏈：強制重塑？ -> 索引是否存在？ -> 文件是否有變動？ -> 最終決定全量、增量或靜默加載。
    """
    current_manifest = get_source_manifest(str(settings.DATA_UPLOAD_DIR))
    index_exists = (settings.VECTOR_DB_DIR / "index.faiss").exists()

    # 指紋對比邏輯
    saved = _get_saved_manifest()
    has_diff = any(current_manifest.get(f) != saved.get(f) for f in current_manifest) or len(current_manifest) != len(
        saved)

    if force_rebuild:
        return _execute_full_rebuild(current_manifest)
    elif not index_exists or has_diff:
        # 如果是第一次運行或檢測到資產變動，自動執行增量同步
        return _execute_incremental_sync(current_manifest)
    else:
        # 靜默加載：資產完全一致時，直接從磁盤讀取加載到內存單例
        global _CACHED_VECTORSTORE
        if _CACHED_VECTORSTORE is None:
            _CACHED_VECTORSTORE = FAISS.load_local(str(settings.VECTOR_DB_DIR), embeddings,
                                                   allow_dangerous_deserialization=True)
            logger.info("📡 [熱加載] 資產指紋 100% 吻合，索引加載成功。")
        return _CACHED_VECTORSTORE


# ==========================================
# 指紋清單 IO：系統的「記憶」
# ==========================================
def _get_saved_manifest() -> Dict:
    """從向量庫目錄讀取上次保存的指紋清單"""
    m_path = settings.VECTOR_DB_DIR / "manifest.json"
    if m_path.exists():
        with open(m_path, "r", encoding="utf-8") as f: return json.load(f)
    return {}


def _save_manifest(m: Dict):
    """將當前指紋清單持久化到磁盤"""
    m_path = settings.VECTOR_DB_DIR / "manifest.json"
    m_path.parent.mkdir(parents=True, exist_ok=True)
    with open(m_path, "w", encoding="utf-8") as f:
        json.dump(m, f, indent=2, ensure_ascii=False)