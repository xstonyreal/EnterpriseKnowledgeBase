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

# ==========================================
# 0. 2026 UI 规范常量 (强制规避废弃 API)
# ==========================================
# 严格禁止使用 use_container_width=True，必须使用以下常量
UI_WIDTH_STRETCH= 'stretch'  # 铺满容器
UI_WIDTH_CONTENT = 'content'  # 自适应内容


# ==========================================
# 1. 启动逻辑与物理状态预检 (核心优化点)
# ==========================================

def get_dynamic_domains():
    """动态获取业务域：通过物理文件夹结构反向映射 UI 选项"""
    _base_dir = settings.DATA_UPLOAD_DIR
    default_domains = ["核心决策层", "未分类资产"]
    if not os.path.exists(_base_dir):
        os.makedirs(_base_dir, exist_ok=True)
        return default_domains

    # 扫描物理子目录作为业务域，实现“文件夹即权限”
    existing_dirs = [
        d for d in os.listdir(_base_dir)
        if os.path.isdir(os.path.join(_base_dir, d)) and not d.startswith(('.', '_'))
    ]
    return sorted(list(set(default_domains + existing_dirs)))


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
    domains = get_dynamic_domains()
    selected_domain = st.selectbox("目标业务域", domains + ["+ 新增业务域..."])

    if selected_domain == "+ 新增业务域...":
        new_domain = st.text_input("请输入新业务域名称")
        if new_domain:
            selected_domain = new_domain

    uploaded_assets = st.file_uploader("注入资产 (PDF/TXT)", type=["pdf", "txt"], accept_multiple_files=True)

    # 【用户主动触发】：接入指纹识别后的智能同步
    if st.button("同步至认知空间", type="primary", width=UI_WIDTH_STRETCH):
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
            check_manifest=True)
            status.update(label="✅ 认知空间已同步", state="complete")
        # 强制重跑，是右侧看板警告消失
        st.rerun()

    st.markdown("---")

    # 强制全量审计依然保留 force_rebuild=True，作为最终兜底手段
    if st.button("🔄 强制执行全量索引审计", width=UI_WIDTH_STRETCH):
        with st.status("⚡ 认知空间自愈中...", expanded=True) as status:
            st.session_state.knowledge_engine = initialize_knowledge_base(force_rebuild=True)
            status.update(label="🎉 索引重塑完成", state="complete")
        st.toast("全量索引已重建")

    if st.button("🗑️ 清空交互上下文", width=UI_WIDTH_STRETCH):
        st.session_state.messages = []
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

                for chunk in stream_gen:
                    full_response += chunk
                    response_placeholder.markdown(full_response + "▌")
                response_placeholder.markdown(full_response)

                if sources:
                    with st.expander("🎓 认知溯源 (Provenance)", expanded=True):
                        for src in sources: st.info(f"📄 来源资产：`{src}`")

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
    if os.path.exists(os.path.join(settings.VECTOR_DB_DIR, "manifest.json")):
        try:
            with open(os.path.join(settings.VECTOR_DB_DIR, "manifest.json"), "r", encoding="utf-8") as f:
                manifest_data = json.load(f)
        except Exception:
            manifest_data = {}

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