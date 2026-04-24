# app/services/ingest_service.py
import os
import json
import time
import threading # 新增：用于线程锁
import tiktoken  # 用于精准 Token 预算
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Tuple
# from app.services.watcher_service import start_sentinel # 從watcher引入哨兵

#  【必须先加载环境】
from dotenv import load_dotenv
load_dotenv() # 必须在所有 getenv 之前运行！

from app.config import settings
from app.core.logger import logger
from langchain_community.vectorstores import FAISS
from app.models.embeddings import embeddings
from langchain_core.documents import Document

# 【变量归位】哨兵和增量逻辑公用的“地图”
# 这里直接从环境变量拿，确保全局可见
DATA_UPLOAD_DIR = os.getenv("DATA_UPLOAD_DIR")
VECTOR_DB_DIR = os.getenv("VECTOR_DB_DIR")

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

# -------------指纹读写--------------------------
def get_saved_manifest() -> Dict[str, str]:
    """读取上一次成功索引时的文件指纹快照"""
    if os.path.exists(MANIFEST_FILE):
        try:
            with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"⚠️ [快照损坏] 无法读取指纹清单: {e}")
    return {}
# -----------------持久化指纹----------------------------
def save_manifest(manifest: Dict[str, str]):
    """持久化当前文件指纹快照"""
    try:
        os.makedirs(os.path.dirname(MANIFEST_FILE), exist_ok=True)
        with open(MANIFEST_FILE, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
        logger.info("💾 [快照归档] 指纹清单已物理固化。")
    except Exception as e:
        logger.error(f"❌ [IO错误] 无法保存指纹清单: {e}")

# *******专用检查工具函数，发现MD5是否一致***********
def _get_manifest_diff() -> Tuple[Dict[str, str], int, bool]:
    """[自省层] 差异分析逻辑抽象，返回 (当前指纹, 差异总数, 是否存在差异)"""
    current_manifest = get_source_manifest(settings.DATA_UPLOAD_DIR)
    saved_manifest = get_saved_manifest()

    added = [f for f in current_manifest if f not in saved_manifest]
    removed = [f for f in saved_manifest if f not in current_manifest]
    changed = [f for f in current_manifest if f in saved_manifest and current_manifest[f] != saved_manifest[f]]

    total_diff = len(added) + len(removed) + len(changed)
    return current_manifest, total_diff, total_diff > 0

# 切片入库
def _handle_rebuild_logic(documents: List[Document], current_manifest: Dict[str, str]) -> FAISS:
    """[执行层] 向量化重塑的核心任务逻辑"""
    logger.info(f"📊 [负载感知] 待处理切片: {len(documents)}，批次规模: {settings.INGEST_BATCH_SIZE}")
    vectorstore = None
    start_time = time.time()

    for i in range(0, len(documents), settings.INGEST_BATCH_SIZE):
        batch = documents[i: i + settings.INGEST_BATCH_SIZE]

        # --- [优化注入：Token 负载感知] ---
        batch_tokens = sum(doc.metadata.get("token_count", 500) for doc in batch)
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

    if vectorstore:
        # 使用统一的全局 db_path
        os.makedirs(db_path, exist_ok=True)
        vectorstore.save_local(db_path)
        save_manifest(current_manifest)

        duration = time.time() - start_time
        logger.info(f"✅ [重塑成功] 耗时: {duration:.2f}s | 状态: 索引与指纹已双向锁定。")

    return vectorstore

# 负责多线程解析
def _parallel_load_and_split() -> List[Document]:
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
    1. 核心：废弃全量扫描，仅对 Added/Changed 名单进行 IO 读写,识别 Deleted 名单，执行向量库物理剔除
    2. 调整后的执行序：引擎挂载 -> 资产审计 -> 哨兵激活
    """
    global _CACHED_VECTORSTORE
    # 场景日志统一输出
    print(f"\n========================= 🔄 [场景2: 增量同步更新] =========================")

    try:
        from app.pipeline.ingest import process_file_to_docs
        start_time = time.time()

        # 1. 提取变动名单
        saved_manifest = get_saved_manifest()
        added_or_changed = [f for f, md5 in current_manifest.items() if saved_manifest.get(f) != md5]
        # 【新增】识别已删除的文件
        deleted_files = [f for f in saved_manifest.keys() if f not in current_manifest]

        if not added_or_changed and not deleted_files:
            logger.info("📡 [增量中止] 检测到指纹一致，无须执行物理更新。")
            return _CACHED_VECTORSTORE
        logger.info(f"🎯 [增量決策] 識別到變動: 增/改 {len(added_or_changed)} | 刪除 {len(deleted_files)}")

        # 2. 状态感知日志：明确告知即将处理的任务量
        logger.info(f"🎯 [增量决策] 识别到变动资产: {len(added_or_changed)} 个 | 准备执行原子化解析...")

        # 确保内存或磁盘中有基础索引
        if _CACHED_VECTORSTORE is None:
            index_path = os.path.join(db_path, "index.faiss")
            if os.path.exists(index_path):
                logger.info("📂 [單例掛載] 正在加載現有索引...")
                _CACHED_VECTORSTORE = FAISS.load_local(db_path, embeddings, allow_dangerous_deserialization=True)
            else:
                logger.warning("⚠️ [索引缺失] 磁盤未發現 index.faiss，降級為全量重塑。")
                return _execute_full_rebuild(current_manifest)

            # 2. 【解析層】局部解析 (僅針對 Added/Changed 文件)
        incremental_docs = []
        for idx, file_path in enumerate(added_or_changed):
            if not os.path.exists(file_path): continue

            logger.info(f"🔄 [解析中] ({idx + 1}/{len(added_or_changed)}) -> {os.path.basename(file_path)}")
            docs = process_file_to_docs(file_path)
            if docs:
                for d in docs:
                    d.metadata["token_count"] = get_token_count(d.page_content)
                    # 確保 Metadata 中刻錄的 Key 是歸一化後的路徑
                    d.metadata["source"] = os.path.normpath(file_path)
                incremental_docs.extend(docs)

        # 3. 【執行層】物理寫庫 (加鎖執行區，確保原子性)
        with _DB_RW_LOCK:
            write_start = time.time()

            # --- 動作 A: 處理移除 (身份定位與物理剔除) ---
            if deleted_files:
                for f in deleted_files:
                    target_key = os.path.normpath(f)
                    # 手動從 docstore 檢索 ID，解決 FAISS 高級 API 報錯問題
                    # noinspection PyProtectedMember
                    ids_to_delete = [
                        # noinspection PyProtectedMember
                        k for k, doc in _CACHED_VECTORSTORE.docstore._dict.items()
                        if os.path.normpath(doc.metadata.get("source", "")) == target_key
                    ]

                    if ids_to_delete:
                        _CACHED_VECTORSTORE.delete(ids=ids_to_delete)
                        logger.info(f"🗑️ [清理完成] 已剔除失效資產: {os.path.basename(f)} ({len(ids_to_delete)} 切片)")
                    else:
                        logger.warning(f"⚠️ [清理跳過] 向量庫中未發現文件 {os.path.basename(f)} 的關聯記錄。")

            # --- 動作 B: 處理新增/修改 ---
            if incremental_docs:
                _CACHED_VECTORSTORE.add_documents(incremental_docs)
                logger.info(f"📊 [追加完成] 累計寫入 {len(incremental_docs)} 個新切片")

            # 4. 【固化層】持久化狀態 (先存庫，後存指紋)
            _CACHED_VECTORSTORE.save_local(db_path)
            save_manifest(current_manifest)

            write_duration = time.time() - write_start
            logger.info(f"💾 [固化成功] 磁盤 IO 耗時: {write_duration:.2f}s")

        total_duration = time.time() - start_time
        logger.info(f"✅ [同步成功] 總耗時: {total_duration:.2f}s | 系統狀態已恢復一致。")
        return _CACHED_VECTORSTORE

    except Exception as e:
        # 补齐异常堆栈，解决你说的“消灭一个出来两个”时排查难的问题
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
    print(f"\n========================= 🚀 [场景3: 全量重塑] =========================")
    try:
        # from app.services.ingest_service import _parallel_load_and_split
        # 这里的函数是扫描全量目录的
        all_docs = _parallel_load_and_split()
        if not all_docs: return None

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
    【RAG 核心调度指挥部 - 三级降级算法】

    设计背景 (Lifecycle Logic):
    Streamlit 是基于“脚本全量重刷”机制运行的。用户每次在 UI 上的交互(如点击按钮)
    都会导致此函数被重新执行。为了避免日志混乱、线程堆积和重复计算，
    我们采用了“单例哨兵 + 指纹比对 + 场景回响”的设计。
    """
    global _CACHED_VECTORSTORE

    # --- 第一步：状态感知 (State Awareness) ---
    # 1. current_manifest: 实时扫描 ./data/uploads 得到的最新 MD5 指纹。
    # 2. has_diff: 对比磁盘 manifest.json，判断 total_diff 是否 > 0 (资产变动)。
    # 3. index_exists: 物理检查 index.faiss 是否存在 (环境完整性)。
    current_manifest, diff_count, has_diff = _get_manifest_diff()
    index_exists = os.path.exists(os.path.join(db_path, "index.faiss"))

    # --- 第二步：三级分流决策 (Dispatcher Logic) ---
    # 定义临时变量用于承接结果，确保 start_sentinel 能在最后统一激活
    result_vs = None

    # 【场景 1: 优先级最高 - 强制全量重塑】
    # 触发条件：用户点击 UI 上定义的 force_rebuild 按钮 (传入 True)。
    # 动作：无视 MD5 指纹，彻底物理重建索引。
    if force_rebuild:
        result_vs = _execute_full_rebuild(current_manifest)

    # 【场景 2: 优先级中等 - 环境异动/增量更新】
    # 触发条件：
    #   A. 磁盘索引缺失 (not index_exists) —— 兜底物理丢失风险。
    #   B. 检测到指纹差异 (has_diff) —— 响应资产内容的 增/删/改。
    elif not index_exists or (has_diff and check_manifest):
        # 动作：执行手术刀式的“局部向量化”，并追加到现有索引。
        _CACHED_VECTORSTORE = _execute_incremental_sync(current_manifest)

        # 只有在成功获取对象后，才归档指纹，防止“账过了货没到”
        if _CACHED_VECTORSTORE:
            from app.services.ingest_service import save_manifest
            save_manifest(current_manifest)
            logger.info("✨ [同步閉環] 向量庫已更新並固化。")

    # 【场景 3: 优先级最低 - 资产状态一致】
    # 触发条件：以上所有变动条件均不成立 (force为False，索引完好，MD5全对)。
    else:
        # [核心设计 - 回响机制]: 即使不干活，也必须打印明确的 Log Info。
        # 原因：为了满足用户“点击必有回应”的需求，让前端在测试阶段能明确感知到“系统已自检”。
        print(f"\n————————————————————————— 🎯 [场景3: 资产状态一致] —————————————————————————")
        logger.info("📡 [自检回响] 本地资产 MD5 与索引指纹 100% 吻合，系统保持静默。")

        # 内存单例加载逻辑
        if _CACHED_VECTORSTORE is None and index_exists:
            with _DB_RW_LOCK:  # 互斥锁确保在多线程交互下，内存对象的赋值是线程安全的
                if _CACHED_VECTORSTORE is None:
                    _CACHED_VECTORSTORE = FAISS.load_local(
                        db_path,
                        embeddings,
                        allow_dangerous_deserialization=True
                    )
        result_vs = _CACHED_VECTORSTORE

    # --- 第三步：【逻辑闭环】激活实时监控哨兵 ---
    # 修正逻辑：必须放在分流逻辑之后，确保“先审计，后监控”的日志序位。
    from app.services.watcher_service import start_sentinel
    start_sentinel()

    return _CACHED_VECTORSTORE

    # [辅助逻辑注释：去抖动策略]
    # 在 start_sentinel 的 while True 循环中必须包含 time.sleep(0.5)。
    # 原因：合并操作系统高频产生的 IO 修改事件信号（去抖 Debounce），
    # 确保 has_diff 的判断发生在文件写入完成后的稳定状态。