# app_ui.py
import streamlit as st
import pandas as pd
from datetime import datetime
import os
import json
from pathlib import Path
# --- [架构级引用] ---
from app.services.ingest_service import initialize_knowledge_base, MANIFEST_FILE, get_saved_manifest
from app.pipeline.watcher import get_source_manifest # 确保引入指纹扫描工具
from app.services.watcher_service import start_sentinel
from app.core.engine import get_chat_response_stream
from app.config import settings
from app.services.domain_service import (
    init_domains,
    get_active_domains,
    get_all_domains,
    create_domain,
    update_domain,
    delete_domain,
    sync_physical_to_json
)
from app.ui_logger import add_ui_log, clear_ui_logs, get_ui_logs
add_ui_log("🔥 开始全量重建")
add_ui_log("📄 加载文件: test.txt")
add_ui_log("✅ 同步完成")

print("當前磁盤指紋:")
current = get_source_manifest(settings.DATA_UPLOAD_DIR)
for k, v in current.items():
    print(f"  {k}: {v}")

print("\n保存的指紋:")
saved = get_saved_manifest()
for k, v in saved.items():
    print(f"  {k}: {v}")

print(f"\n是否一致: {current == saved}")


# ==========================================
# 0. 2026 UI 规范常量 (强制规避废弃 API)
# ==========================================
# 严格禁止使用 use_container_width=True，必须使用以下常量
UI_WIDTH_STRETCH= "stretch"  # 铺满容器
UI_WIDTH_CONTENT = "content"  # 自适应内容

# ==========================================
# 0. 启动定时任务（每日凌晨 2:00 全量重建）  ← 加在这里
# ==========================================
from app.scheduler import start_daily_rebuild
start_daily_rebuild()

# ==========================================
# 1. 启动逻辑与物理状态预检 (核心优化点) 暫時廢除
# ==========================================
# 初始化域數據
if "domains_initialized" not in st.session_state:
    init_domains()
    st.session_state.domains_initialized = True

# --- [冷热启动拦截器] ---
# 目的：防止启动时因磁盘无索引而触发耗时的“全量重塑”动作
# 无论磁盘文件怎么变，启动时我们只尝试加载 index.faiss，只要索引存在，就正常加载
db_index_path = os.path.join(settings.VECTOR_DB_DIR, "index.faiss")
index_exists = os.path.exists(db_index_path)

# 初始化引擎：只有在索引物理存在时，才进行热加载
if "knowledge_engine" not in st.session_state:
    if index_exists:
        # heck_manifest=False，禁止启动时自动对比指纹，秒级热加载现有资产
        st.session_state.knowledge_engine = initialize_knowledge_base(force_rebuild=False, check_manifest=False)
    else:
        # 拦截！磁盘无索引时保持 None，将重塑权交给用户的“同步”按钮
        st.session_state.knowledge_engine = None

# 初始化哨兵 (保持后台监听)
if "sentinel_active" not in st.session_state:
    start_sentinel()
    st.session_state.sentinel_active = True

# ==========================================
# 2. 页面基础配置
# ==========================================
st.set_page_config(page_title="Matrix Intelligence", page_icon="🛡️", layout="wide")

# 极致视觉化调整
st.markdown("""
    <style>
    .stDeployButton {display:none;}
    footer {visibility: hidden;}
    [data-testid="stHeader"] {background: rgba(0,0,0,0);}
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 3. 侧边栏：资产控制中心 (逻辑中控)
# ==========================================
with st.sidebar:
    st.title("🛡️ 认知治理中心")
    status_color = "🟢" if st.session_state.sentinel_active else "🔴"
    st.caption(f"Status: {status_color} Active (Sentinel Sensing...)")
    st.markdown("---")

    st.subheader("📥 知识资产注入")
    # domains = get_dynamic_domains() 廢除通過物理文件夾來獲取域的信息
    # 使用 domain_service 获取域列表
    domains = get_active_domains()

    if not domains:
        st.warning("⚠️ 暂无业务域，请先在下方「系统管理」中创建")
        selected_domain = "未分类资产"
    else:
        selected_domain = st.selectbox("目標業務域", domains + ["+ 新增業務域..."])

    if selected_domain == "+ 新增业务域...":
        new_domain = st.text_input("请输入新业务域名称")
        if new_domain:
            selected_domain = new_domain
    # 上傳的文檔支持類型
    uploaded_assets = st.file_uploader("注入资产 (PDF/TXT/DOCX/XLSX/PPTX)", type=["pdf", "txt", "docx", "xlsx", "pptx"], accept_multiple_files=True)

    # 【用户主动触发】：接入指纹识别后的智能同步
    if st.button("同步至认知空间", type="primary", width=UI_WIDTH_STRETCH):
        # 清空旧日志，开始新任务
        clear_ui_logs()

        # A. 物理保存 (仅当 通过UI 上传新文件时)
        if uploaded_assets:
            save_path = os.path.join(settings.DATA_UPLOAD_DIR, selected_domain)
            os.makedirs(save_path, exist_ok=True)
            for asset in uploaded_assets:
                with open(os.path.join(save_path, asset.name), "wb") as f:
                    f.write(asset.getbuffer())
            st.toast(f"✅ 已物理接收 {len(uploaded_assets)} 个新文件", icon="📥")

        # B. 智能同步 (无论有无新文件都触发，移出嵌套)
        with st.status("🛠️ 正在执行资产自省与向量化...", expanded=True) as status:
            st.write("📡 正在比对文件指纹 (MD5)...")

            # 在控制台打印，用于确认按钮是否真的被点击了
            print("🚀 [UI交互] 同步按钮被点击，开始调用 initialize_knowledge_base")

            # force_rebuild=False: 允许系统“变聪明”，没变动就不重构。
            # check_manifest=True: (默认值) 强制进行磁盘扫描，指纹对比，确保能发现新上传的文件。
            st.session_state.knowledge_engine = initialize_knowledge_base(force_rebuild=False,
            check_manifest=True, is_ui_click=True)
            status.update(label="✅ 认知空间已同步", state="complete")
        # 强制重跑，是右侧看板警告消失
        # st.rerun() DS suggest del

    st.markdown("---")

    # ========== 实时日志面板 ==========
    with st.expander("📋 实时运行日志", expanded=False):
        col1, col2 = st.columns([3, 1])
        with col2:
            if st.button("🗑️ 清空", use_container_width=True):
                clear_ui_logs()
                st.rerun()

        logs = get_ui_logs()
        if logs:
            # 使用 code 块显示，保持等宽字体
            log_text = "\n".join(logs[-50:])
            st.code(log_text, language="log", line_numbers=False)
        else:
            st.caption("暂无日志，请点击同步按钮开始...")

        st.caption(f"📊 共 {len(logs)} 条日志")
    # ========== 实时日志面板 ==========

    # 强制全量索引审计按钮
    if st.button("🔄 强制执行全量索引审计", use_container_width=True):
        with st.status("⚡ 认知空间自愈中...", expanded=True) as status:
            st.session_state.knowledge_engine = initialize_knowledge_base(force_rebuild=True)
            status.update(label="🎉 索引重塑完成", state="complete")
        st.toast("全量索引已重建")

    # ========== 管理員面板（摺疊） ==========
    with st.expander("🔧 系統管理 (域配置)", expanded=False):
        st.subheader("🏷️ 業務域管理")

        # ---------- 新增域表單 ----------
        with st.form("add_domain_form"):
            st.caption("新增業務域")
            col1, col2 = st.columns([3, 1])
            with col1:
                new_name = st.text_input("域名稱", key="new_domain_name", placeholder="例如: 財務部")
            with col2:
                new_desc = st.text_input("描述（可選）", key="new_domain_desc", placeholder="簡要描述")

            submitted = st.form_submit_button("➕ 新增域", use_container_width=True)

            if submitted and new_name:
                if create_domain(new_name.strip(), new_desc):
                    st.success(f"✅ 已創建域: {new_name}")
                    st.rerun()
                else:
                    st.error("創建失敗，域名稱可能已存在")

        st.divider()

        # ---------- 現有域列表 ----------
        st.caption("現有業務域")
        all_domains = get_all_domains()

        if not all_domains:
            st.info("暫無業務域，請先創建")
        else:
            for domain in all_domains:
                col1, col2, col3, col4 = st.columns([2, 2, 1.5, 1])

                with col1:
                    if domain["status"] == "deleted":
                        st.markdown(f"~~{domain['name']}~~")
                    else:
                        st.text(domain["name"])

                with col2:
                    desc = domain.get("description", "")
                    st.caption(desc[:40] + "..." if len(desc) > 40 else desc)

                with col3:
                    status_text = "🟢 啟用" if domain["status"] == "active" else "⚪ 已禁用"
                    st.caption(status_text)

                with col4:
                    if domain["status"] == "active":
                        if st.button(f"🗑️ 禁用", key=f"del_{domain['name']}"):
                            delete_domain(domain["name"], hard=False)
                            st.rerun()
                    else:
                        # 軟刪除的域可以恢復
                        if st.button(f"🔄 恢復", key=f"res_{domain['name']}"):
                            update_domain(domain["name"], reactivate=True)
                            st.rerun()

        # ---------- 高級操作（可摺疊）----------
        with st.expander("⚠️ 高級操作", expanded=False):
            st.caption("硬刪除會同時刪除物理文件夾，不可恢復")

            # 顯示可硬刪除的域
            deleted_domains = [d for d in all_domains if d.get("status") == "deleted"]
            if deleted_domains:
                for domain in deleted_domains:
                    if st.button(f"🔥 徹底刪除 {domain['name']}", key=f"hard_del_{domain['name']}"):
                        delete_domain(domain["name"], hard=True)
                        st.rerun()
            else:
                st.caption("暫無可徹底刪除的域")

            st.divider()

            # 手動同步物理文件夾
            if st.button("🔄 同步物理文件夾", use_container_width=True):
                count = sync_physical_to_json()
                if count > 0:
                    st.success(f"✅ 已同步 {count} 個新文件夾")
                else:
                    st.info("無新增文件夾")
                st.rerun()

# ==========================================
# 4. 主界面：智慧交互与溯源
# ==========================================
col_chat, col_history = st.columns([3, 2], gap="large")

with col_chat:
    st.title("🧩 智慧交互决策中心")

    # 引导性逻辑：如果检测到索引为空，给予用户明确指引
    if st.session_state.knowledge_engine is None:
        st.warning("📭 **当前认知空间为空**。请在左侧侧边栏上传资产并点击『同步』以激活知识库。")

    st.caption(f"Domain Filtering: ON | Active Area: {selected_domain}")

    if "messages" not in st.session_state:
        st.session_state.messages = []

    # 渲染历史消息
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            if "sources" in message and message["sources"]:
                with st.expander("📚 参考来源"):
                    for s in message["sources"]: st.caption(f"📍 {s}")

    # 聊天驱动逻辑
    if prompt := st.chat_input("请键入业务指令..."):
        if st.session_state.knowledge_engine is None:
            st.error("无法处理请求：请先同步资产构建索引。")
        else:
            st.session_state.messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)

            with st.chat_message("assistant"):
                response_placeholder = st.empty()
                full_response = ""
                # 传入 Domain 过滤器，实现物理隔离检索
                stream_gen, sources = get_chat_response_stream(prompt, filter_domain=selected_domain)

                # DS TEST
                # print("DEBUG sources:", sources)

                for chunk in stream_gen:
                    full_response += chunk
                    response_placeholder.markdown(full_response + "▌")
                response_placeholder.markdown(full_response)
                # test
                # st.write(f"DEBUG: sources 長度 = {len(sources)}")

                if sources:
                    with st.expander("🎓 認知溯源 (Matrix Provenance)", expanded=True):
                        # 這裡假設後台傳回來的 sources 已經升級為 Dict 列表
                        # 格式示例: [{"source": "xxx.pdf", "score": 0.12, "content": "..."}]

                        cols = st.columns(len(sources) if len(sources) > 0 else 1)
                        for idx, doc_info in enumerate(sources):
                            # 兼容性處理：如果後台還沒改好，依然支持純字符串
                            is_dict = isinstance(doc_info, dict)
                            src_name = doc_info.get("source", "未知來源") if is_dict else doc_info
                            score = doc_info.get("score", 0.0) if is_dict else 0.0
                            content = doc_info.get("content", "") if is_dict else ""

                            with cols[idx % len(cols)]:
                                # 計算匹配百分比 (FAISS L2 距離越小越好，這裡做個視覺轉換)
                                display_score = max(0, int((1 - score) * 100))

                                st.markdown(f"""
                                                <div style="padding:10px; border-radius:5px; border-left:5px solid #2ecc71; background-color:rgba(46, 204, 113, 0.1); margin-bottom:10px">
                                                    <div style="font-size:0.8rem; font-weight:bold; color:#27ae60;">MATCH: {display_score}%</div>
                                                    <div style="font-size:0.9rem; margin-top:5px;">📄 {os.path.basename(src_name)}</div>
                                                </div>
                                                """, unsafe_allow_html=True)

                                if content:
                                    st.caption(f"📝 關鍵片段預覽:")
                                    st.code(f"...{content[:100]}...", wrap_lines=True)

            st.session_state.messages.append({
                "role": "assistant",
                "content": full_response,
                "sources": sources
            })

# ==========================================
# 5. 右侧面板：资产审计看板 (数据可视化)
# ==========================================
with col_history:
    st.title("📊 知识资产审计")

    # [新增：预警雷达逻辑,这里直接比对磁盘和上次同步后的快照]
    from app.services.ingest_service import get_saved_manifest, get_source_manifest

    # 实时计算当前磁盘指纹，并读取上次固化的指纹
    _current_m = get_source_manifest(settings.DATA_UPLOAD_DIR)
    _saved_m = get_saved_manifest()

    # 如果不一样，仅报警
    if _current_m != _saved_m:
        st.warning("⚠️ **检测到资产变动**：磁盘文件与现有索引不一致。建议点击左侧『同步』按钮进行全量审计。")

    # --- [新增逻辑]：为了判断状态，先读取指纹快照 ---
    manifest_data = get_saved_manifest()

    asset_history = []
    base_dir = settings.DATA_UPLOAD_DIR

    # 物理资产实时嗅探
    if os.path.exists(base_dir):
        for root, _, files in os.walk(base_dir):
            for file in files:
                if not file.startswith(('.', '~')):
                    f_path = os.path.join(root, file)
                    rel_path = os.path.relpath(root, base_dir)

                    # --- 核心逻辑：计算该文件在 manifest 中的 Key ---
                    # 如果是根目录文件，Key 就是文件名；如果是子目录，Key 是 "子目录/文件名"
                    dict_key = os.path.join(rel_path, file) if rel_path != "." else file
                    # 统一使用正斜杠，防止 Windows/Linux 路径差异导致的匹配失败
                    dict_key = dict_key.replace("\\", "/")

                    is_indexed = "✅ 已固化" if dict_key in manifest_data else "⏳ 待同步"

                    asset_history.append({
                        "资产名称": file,
                        "业务维度": rel_path if rel_path != "." else "未分类资产",
                        "状态": is_indexed,  # 💡 这是新增的列
                        "规模": f"{os.stat(f_path).st_size / 1024:.1f} KB",
                        "最近审计时间": datetime.fromtimestamp(os.stat(f_path).st_mtime).strftime("%Y-%m-%d %H:%M")
                    })

    if asset_history:
        # 保持你原来的排序字段：最近审计时间
        df = pd.DataFrame(asset_history).sort_values(by="最近审计时间", ascending=False)
        # 使用 stretch 常量，确保宽屏显示效果
        st.dataframe(df, width=UI_WIDTH_STRETCH, hide_index=True)
        st.divider()
        st.metric("集成资产总量", f"{len(asset_history)} Units")
    else:
        st.info("📂 暂无资产集成记录。")