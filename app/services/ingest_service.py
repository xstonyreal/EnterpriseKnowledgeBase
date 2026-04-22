# app/services/ingest_service.py
import os
import json
import time
import threading # 新增：用于线程锁
import tiktoken  # 用于精准 Token 预算
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict

from app.config import settings
from app.core.logger import logger
from langchain_community.vectorstores import FAISS
from app.models.embeddings import embeddings
from langchain_core.documents import Document

# 导入新增的指纹工具与扫描逻辑
from app.pipeline.watcher import get_source_manifest

# --- 并发执行策略设定 ---

# 设定 MAX_WORKERS 的设计逻辑：统一并发阈值：取核心数+4与12的最小值
# 1. 行业标准：IO密集型任务通常设为 CPU核心数 * 5，但 RAG 包含计算密集型的 Token 计数。
# 2.  选型：取核心数 + 4 与 12 之间的最小值，确保在本地 8-16 核机器上表现最稳。
MAX_WORKERS = min(12, (os.cpu_count() or 1) + 4)

# 单次 Embedding 批次上限设计逻辑：
# 1. 性能平衡：批次过小网络开销大，批次过大易超时。
# 2. 经验值：OpenAI 与 LangChain 社区实践证明 2000-4000 token 是吞吐量最优区间。
BATCH_TOKEN_LIMIT = 3000

# [架构级锁定]：全局单例变量
# 作用：根治 Streamlit 环境下因多次初始化导致的日志重复和内存浪费
_CACHED_VECTORSTORE = None
_LOCK = threading.Lock() # 新增：确保单例赋值时的线程安全

# 【状态协议】：指纹快照存储路径，位于向量库同级目录
db_path = settings.VECTOR_DB_DIR  # 统一使用这个变量
MANIFEST_FILE = os.path.join(db_path, "manifest.json")

# 初始化 Token 计数器
try:
    _ENCODER = tiktoken.get_encoding("cl100k_base")
except:
    _ENCODER = tiktoken.get_encoding("gpt2")

def get_token_count(text: str) -> int:
    """计算字符串的精确 Token 数量"""
    return len(_ENCODER.encode(text))

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


def initialize_knowledge_base(force_rebuild=False, check_manifest=True):
    """具备【指纹对比】、【单例自省】与【硬核诊断】能力的初始化服务"""
    global _CACHED_VECTORSTORE

    db_path = settings.VECTOR_DB_DIR
    index_file = os.path.join(db_path, "index.faiss")

    # ================= [第一步：动作 - 纯粹的现状感知] =================
    # 1. 预先获取指纹，用于判断
    current_manifest = get_source_manifest(settings.DATA_UPLOAD_DIR)
    saved_manifest = get_saved_manifest()

    # --- 新增：差异汇总逻辑，用于判断是否需要提供用户手工同步 ---
    added = [f for f in current_manifest if f not in saved_manifest]
    removed = [f for f in saved_manifest if f not in current_manifest]
    changed = [f for f in current_manifest if f in saved_manifest and current_manifest[f] != saved_manifest[f]]

    # 只要这三个列表都为空，就是真正的“内容无差异”
    total_diff_count = len(added) + len(removed) + len(changed)
    has_diff = len(added) + len(removed) + len(changed) > 0

    # 2. 重新定义拦截逻辑
    # 只有在 (内存有值) 且 (不强制重构) 且 (不需要检查指纹 或 指纹没变) 的情况下，才拦截
    if _CACHED_VECTORSTORE is not None and not force_rebuild:
        if not check_manifest or not has_diff :
            # 只有这时候才能真的拦截返回
            return _CACHED_VECTORSTORE

    # ================= [手术刀调试打印 - 优化版] =================
    print("\n" + "—" * 50)
    print("🔍 [知识库自省] 状态检查启动...")

    # 2. 【行动阶段】：根据差异事实，分三种状态执行
    # 根据事实(has_diff) 和 模式(check_manifest) 决定执行动作

    # 场景 A：内容完全一致 -> 永远执行秒开 (无论 check_manifest 是啥)
    if not has_diff:
        # 秒开模式下的逻辑
        needs_rebuild = force_rebuild or not os.path.exists(index_file)
        print("🎯 状态: [内容完全一致] (MD5 验证通过)")
        print(f"🚩 决策: {'重建索引' if needs_rebuild else '直接进入系统'}")
    # 场景 B：MD5检查发现差异,待用户手工同步

    elif not check_manifest:
        if check_manifest:
            needs_rebuild = True
            print(f"🔄 [内容变更] 监测到资产变动：新增 {len(added)} | 修改 {len(changed)} |{len(removed)}")
        # 如果是“普通启动”(check_manifest=False)，忽略差异执行秒开
        else:
            needs_rebuild = force_rebuild or not os.path.exists(index_file)
            print(f"🚀 模式: [热加载秒开] (已侦测磁盘 {len(added) + len(changed) +len(removed)} 处差异)")
            print(f"🚩 决策: {'重建索引' if needs_rebuild else '跳过变动，直接进入'}")
    # 3. 【执行层】：根据 needs_rebuild 结果干活
    # 场景 C: MD5存在差异，用户手工触发了同步 ---
    else:
        needs_rebuild = True
        print(f"🔄 模式: [智能同步检查]")
        print(f"📊 比对: 磁盘({len(current_manifest)}) vs 快照({len(saved_manifest)})")
        print(f"🚩 决策: 指纹不一致 = {needs_rebuild}")
    print("—" * 50 + "\n")
    # =========================================================

    # --- 流程 A: 智能热加载 ---
    if not needs_rebuild:
        # 【核心修正】：不要直接写死“完全一致”，要根据 has_diff 分情况说明
        if not has_diff:
            logger.info("🔍 [系统提示] 内容与索引完全一致，执行高速秒开模式...")
        else:
            logger.info(f"🔍 [系统提示] 侦测到 共{total_diff_count}处变动，但依指令执行静默秒开...")

        try:
            # 优先检查内存缓存
            if os.path.exists(db_path):
                _CACHED_VECTORSTORE = FAISS.load_local(db_path, embeddings, allow_dangerous_deserialization=True)

                # 终端打印也要区分事实
                if not has_diff:
                    print("🎯 [逻辑对齐] 磁盘与快照完全吻合，系统直接就绪。")
                else:
                    print(f"🚀 [逻辑对齐] 变动已忽略（共 {total_diff_count} 处差异），系统使用旧索引就绪。")

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
            # 1. 深度扫描深度扫描与并发解析
            logger.info(f"📂 [DEBUG-1] 启动深度扫描模式: {settings.DATA_UPLOAD_DIR}")
            documents: List[Document] = _parallel_load_and_split()

            if not documents:
                logger.warning("⚠️ [认知空间] 扫描完成，未能提取到有效文本。")
                return None

            # 2. 切片分批入库逻辑 (【核心修复】：将循环缩进进 try 块内)
            logger.info(f"📊 [负载感知] 待处理切片: {len(documents)}，批次规模: {settings.INGEST_BATCH_SIZE}")

            vectorstore = None

            for i in range(0, len(documents), settings.INGEST_BATCH_SIZE):
                batch = documents[i: i + settings.INGEST_BATCH_SIZE]
                # --- [优化注入：Token 负载感知] ---
                # 逻辑：检查当前批次总 Token 是否超过安全阈值 (如 6000)，防止 10054 错误
                # 注：需配合 _parallel_load_and_split 中注入的 metadata["token_count"]
                batch_tokens = sum(doc.metadata.get("token_count", 500) for doc in batch)
                if batch_tokens > 6000:
                    logger.warning(f"⚠️ [负载预警] 当前批次 Token ({batch_tokens}) 过高，即将触发降速处理...")
                if batch_tokens > 11000:
                    logger.warning(f"⚠️ [负载过高] 正在进行保护性降速...")
                    time.sleep(2)  # 给显存 2 秒钟的喘息/回收时间，防止温度过高或驱动崩溃
                # -------------------------------

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
                # 优化点：重构成功后使用锁更新单例
                with _LOCK:
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


    time.sleep(0.1)

    # 2. 检查缓存。如果有，直接返还给 UI
    if _CACHED_VECTORSTORE is not None:
        return _CACHED_VECTORSTORE

    # 3. 如果内存缓存没了（比如刚重启），则从磁盘热加载
    if os.path.exists(db_path):
        with _LOCK:
            if _CACHED_VECTORSTORE is None:
                _CACHED_VECTORSTORE = FAISS.load_local(
                    db_path,
                    embeddings,
                    allow_dangerous_deserialization=True
                )
        return _CACHED_VECTORSTORE

    # 4. 只有既不需要重构，磁盘也没索引，才返回 None

    return None