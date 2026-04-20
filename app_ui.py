# app_ui.py
import streamlit as st
import pandas as pd
from datetime import datetime
import os

# --- [架构级引用] ---
from app.services.ingest_service import initialize_knowledge_base
from app.services.watcher_service import start_sentinel
from app.core.engine import get_chat_response_stream
from app.config import settings

# ==========================================
# 0. 2026 UI 规范常量 (强制规避废弃 API)
# ==========================================
# 严格禁止使用 use_container_width=True，必须使用以下常量
UI_WIDTH_STRETCH = 'stretch'  # 铺满容器
UI_WIDTH_CONTENT = 'content'  # 自适应内容


# ==========================================
# 1. 启动逻辑与物理状态预检 (核心优化点)
# ==========================================

def get_dynamic_domains():
    """动态获取业务域：通过物理文件夹结构反向映射 UI 选项"""
    base_dir = settings.DATA_UPLOAD_DIR
    default_domains = ["核心决策层", "未分类资产"]
    if not os.path.exists(base_dir):
        os.makedirs(base_dir, exist_ok=True)
        return default_domains

    # 扫描物理子目录作为业务域，实现“文件夹即权限”
    existing_dirs = [
        d for d in os.listdir(base_dir)
        if os.path.isdir(os.path.join(base_dir, d)) and not d.startswith(('.', '_'))
    ]
    return sorted(list(set(default_domains + existing_dirs)))


# --- [冷热启动拦截器] ---
# 目的：防止启动时因磁盘无索引而触发耗时的“全量重塑”动作
db_index_path = os.path.join(settings.CHROMA_PERSIST_DIR, "faiss_index", "index.faiss")
index_exists = os.path.exists(db_index_path)

# 初始化引擎：只有在索引物理存在时，才进行热加载
if "knowledge_engine" not in st.session_state:
    if index_exists:
        # 秒级热加载现有资产
        st.session_state.knowledge_engine = initialize_knowledge_base(force_rebuild=False)
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

    # 【用户主动触发】：此时才会动用我们优化过的“重度计算引擎”
    if st.button("同步至认知空间", type="primary", width=UI_WIDTH_STRETCH):
        if uploaded_assets:
            save_path = os.path.join(settings.DATA_UPLOAD_DIR, selected_domain)
            os.makedirs(save_path, exist_ok=True)
            for asset in uploaded_assets:
                with open(os.path.join(save_path, asset.name), "wb") as f:
                    f.write(asset.getbuffer())

            with st.status("🛠️ 正在执行资产重塑与分批向量化...", expanded=True) as status:
                st.write("正在扫描物理分片...")
                # 明确要求全量重构
                st.session_state.knowledge_engine = initialize_knowledge_base(force_rebuild=True)
                status.update(label="✅ 资产集成完毕", state="complete")
            st.rerun()

    st.markdown("---")

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
    asset_history = []
    base_dir = settings.DATA_UPLOAD_DIR

    # 物理资产实时嗅探
    if os.path.exists(base_dir):
        for root, _, files in os.walk(base_dir):
            for file in files:
                if not file.startswith(('.', '~')):
                    f_path = os.path.join(root, file)
                    rel_path = os.path.relpath(root, base_dir)
                    asset_history.append({
                        "资产名称": file,
                        "业务维度": rel_path if rel_path != "." else "未分类资产",
                        "规模": f"{os.stat(f_path).st_size / 1024:.1f} KB",
                        "最近审计时间": datetime.fromtimestamp(os.stat(f_path).st_mtime).strftime("%Y-%m-%d %H:%M")
                    })

    if asset_history:
        df = pd.DataFrame(asset_history).sort_values(by="最近审计时间", ascending=False)
        # 使用 stretch 常量，确保宽屏显示效果
        st.dataframe(df, width=UI_WIDTH_STRETCH, hide_index=True)
        st.divider()
        st.metric("集成资产总量", f"{len(asset_history)} Units")
    else:
        st.info("📂 暂无资产集成记录。")