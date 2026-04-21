# app/services/ingest_service.py
import os
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict

from app.config import settings
from app.core.logger import logger
from langchain_community.vectorstores import FAISS
from app.models.embeddings import embeddings
from langchain_core.documents import Document

# 导入新增的指纹工具与扫描逻辑
from app.pipeline.watcher import get_source_manifest

# [架构级锁定]：全局单例变量
# 作用：根治 Streamlit 环境下因多次初始化导致的日志重复和内存浪费
_CACHED_VECTORSTORE = None

# 【状态协议】：指纹快照存储路径，位于向量库同级目录
MANIFEST_FILE = os.path.join(settings.CHROMA_PERSIST_DIR, "manifest.json")


def get_saved_manifest() -> Dict[str, str]:
    """读取上一次成功索引时的文件指纹快照"""
    if os.path.exists(MANIFEST_FILE):
        try:
            with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"⚠️ [快照损坏] 无法读取指纹清单: {e}")
    return {}


def save_manifest(manifest: Dict[str, str]):
    """持久化当前文件指纹快照"""
    try:
        os.makedirs(os.path.dirname(MANIFEST_FILE), exist_ok=True)
        with open(MANIFEST_FILE, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
        logger.info("💾 [快照归档] 指纹清单已物理固化。")
    except Exception as e:
        logger.error(f"❌ [IO错误] 无法保存指纹清单: {e}")


def _parallel_load_and_split() -> List[Document]:
    """并发解析引擎"""
    from app.pipeline.ingest import list_all_files, process_file_to_docs

    files = list_all_files(settings.DATA_UPLOAD_DIR)
    all_docs = []

    if not files:
        logger.warning("📂 数据目录中未发现可处理的文件。")
        return all_docs

    logger.info(f"⚡ [并发引擎] 启动 {settings.INGEST_MAX_WORKERS} 线程并行解析...")

    with ThreadPoolExecutor(max_workers=settings.INGEST_MAX_WORKERS) as executor:
        future_to_file = {executor.submit(process_file_to_docs, f): f for f in files}

        for future in as_completed(future_to_file):
            file_name = future_to_file[future]
            try:
                docs = future.result()
                if docs:
                    all_docs.extend(docs)
            except Exception as e:
                logger.error(f"❌ [原子失效] 文件 {file_name} 解析崩溃: {e}")

    return all_docs


def initialize_knowledge_base(force_rebuild=False, check_manifest=True):
    """具备【指纹对比】、【单例自省】与【硬核诊断】能力的初始化服务"""
    global _CACHED_VECTORSTORE

    db_path = settings.CHROMA_PERSIST_DIR
    index_file = os.path.join(db_path, "index.faiss")

    # 1. 预先获取指纹，用于判断
    current_manifest = get_source_manifest(settings.DATA_UPLOAD_DIR)
    saved_manifest = get_saved_manifest()

    # 2. 重新定义拦截逻辑
    # 只有在 (内存有值) 且 (不强制重构) 且 (不需要检查指纹 或 指纹没变) 的情况下，才拦截
    if _CACHED_VECTORSTORE is not None and not force_rebuild:
        if not check_manifest or (current_manifest == saved_manifest):
            # 只有这时候才能真的拦截返回
            return _CACHED_VECTORSTORE

    # 1. 【一级拦截】：内存单例检查
    # if _CACHED_VECTORSTORE is not None and not force_rebuild:
    #     return _CACHED_VECTORSTORE



    # ================= [手术刀调试打印 - 优化版] =================
    current_manifest = get_source_manifest(settings.DATA_UPLOAD_DIR)
    saved_manifest = get_saved_manifest()

    print("\n" + "—" * 50)
    print("🔍 [知识库自省] 状态检查启动...")

    if not check_manifest:
        # 秒开模式下的逻辑
        needs_rebuild = force_rebuild or not os.path.exists(index_file)
        print(f"🚀 模式: [热加载秒开] (已忽略磁盘 {len(current_manifest)} 个文件的指纹差异)")
        print(f"🚩 决策: {'重建索引' if needs_rebuild else '直接进入系统'}")
    else:
        # 同步模式下的逻辑
        needs_rebuild = force_rebuild or not os.path.exists(index_file) or (current_manifest != saved_manifest)
        print(f"🔄 模式: [智能同步检查]")
        print(f"📊 比对: 磁盘({len(current_manifest)}) vs 快照({len(saved_manifest)})")
        print(f"🚩 决策: 指纹不一致 = {needs_rebuild}")
    print("—" * 50 + "\n")
    # =========================================================

    # --- 流程 A: 智能热加载 ---
    if not needs_rebuild:
        logger.info("🔍 [手术刀] 检测到内容与索引完全一致，执行高速秒开模式...")
        try:
            vectorstore = FAISS.load_local(db_path, embeddings, allow_dangerous_deserialization=True)
            _CACHED_VECTORSTORE = vectorstore
            return _CACHED_VECTORSTORE
        except Exception as e:
            logger.error(f"❌ [风险预警] 索引文件损坏，准备自动执行重构: {e}")
            needs_rebuild = True

    # --- 流程 B: 知识重塑 ---
    current_manifest = get_source_manifest(settings.DATA_UPLOAD_DIR)
    if needs_rebuild:
        logger.info("🏗️ [核心工程] 启动受控知识重塑流程...")
        start_time = time.time()

        try:
            # 1. 深度扫描
            logger.info(f"📂 启动深度扫描模式: {settings.DATA_UPLOAD_DIR}")
            documents: List[Document] = _parallel_load_and_split()

            if not documents:
                logger.warning("⚠️ [认知空间] 扫描完成，未能提取到有效文本。")
                return None

            # 2. 切片分批入库逻辑 (【核心修复】：将循环缩进进 try 块内)
            logger.info(f"📊 [负载感知] 待处理切片: {len(documents)}，批次规模: {settings.INGEST_BATCH_SIZE}")

            vectorstore = None

            for i in range(0, len(documents), settings.INGEST_BATCH_SIZE):
                batch = documents[i: i + settings.INGEST_BATCH_SIZE]
                if vectorstore is None:
                    vectorstore = FAISS.from_documents(batch, embeddings)
                else:
                    vectorstore.add_documents(batch)

                # 进度日志
                if (i // settings.INGEST_BATCH_SIZE) % 5 == 0 or (i + len(batch) >= len(documents)):
                    current_count = i + len(batch)
                    progress = current_count / len(documents) * 100
                    logger.info(f"🚀 [计算中] 向量化进度: {progress:.1f}% ({current_count}/{len(documents)})")

            # 3. 结果物理固化
            if vectorstore:
                if not os.path.exists(db_path):
                    os.makedirs(db_path)

                vectorstore.save_local(db_path)

                # --- 关键修正：确保 current_manifest 是在函数开头或此处最新获取的 ---
                # 只有这里对齐了，下次点击红色按钮才会判定为 False
                # 重新扫描一遍磁盘，确保拿到最准确的 5 个文件指纹

                save_manifest(current_manifest)

                _CACHED_VECTORSTORE = vectorstore

                # 严格保留你的 duration 变量和日志格式
                duration = time.time() - start_time
                logger.info(f"✅ [重塑成功] 耗时: {duration:.2f}s | 状态: 索引与指纹已双向锁定。")
                print("--- 🔄 逻辑已跳回 UI 层执行 Rerun ---")
                time.sleep(0.1)  # <<<<<< [修改 3: 缓冲延迟]
                return _CACHED_VECTORSTORE

        except Exception as e:
            _CACHED_VECTORSTORE = None
            error_info = str(e)
            logger.critical(f"🚨 [系统崩溃] 本地重构失败: {error_info}")

            # 针对性诊断建议 (你的显式声明风格)
            if "10054" in error_info or "Connection" in error_info:
                logger.error("💡 [诊断] 连接异常，请确认 Ollama 已启动。")
            elif "Memory" in error_info or "OOM" in error_info.upper():
                logger.error("💡 [诊断] 显存溢出，请调小 Settings.INGEST_BATCH_SIZE。")

            raise e

    # --- 【强制修复：逻辑终点】 ---
    # 如果代码走到这里，说明 needs_rebuild 为 False（指纹完全一致）

    # 1. 打印“定心丸”，让你在终端能看到结果
    print("🎯 [逻辑对齐] 磁盘与快照完全吻合，已跳过重塑，直接返回现有引擎。")
    import time
    time.sleep(0.1)

    # 2. 检查缓存。如果有，直接返还给 UI
    if _CACHED_VECTORSTORE is not None:
        return _CACHED_VECTORSTORE

    # 3. 如果内存缓存没了（比如刚重启），则从磁盘热加载
    if os.path.exists(db_path):

        _CACHED_VECTORSTORE = FAISS.load_local(
            db_path,
            embeddings,
            allow_dangerous_deserialization=True
        )
        return _CACHED_VECTORSTORE

    # 4. 只有万策尽（既不需要重构，磁盘也没索引）才返回 None

    return None