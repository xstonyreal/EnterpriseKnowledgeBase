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
# 1. 初始化逻辑
# ==========================================
if "knowledge_engine" not in st.session_state:
    st.session_state.knowledge_engine = initialize_knowledge_base(force_rebuild=False)

if "sentinel_active" not in st.session_state:
    start_sentinel()
    st.session_state.sentinel_active = True

# ==========================================
# 2. 全局 UI 配置 (遵循 2026 开发规范)
# ==========================================
st.set_page_config(page_title="Matrix Intelligence", page_icon="🛡️", layout="wide")

st.markdown("""
    <style>
    .stDeployButton {display:none;}
    footer {visibility: hidden;}
    [data-testid="stHeader"] {background: rgba(0,0,0,0);}
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 3. 侧边栏：资产控制
# ==========================================
with st.sidebar:
    st.title("🛡️ 认知治理中心")
    status_color = "🟢" if st.session_state.sentinel_active else "🔴"
    st.caption(f"Status: {status_color} Active")
    st.markdown("---")

    st.subheader("📥 知识资产注入")
    business_domains = ["核心决策层", "财务治理矩阵", "技术研发中枢", "行政合规部", "市场战略部"]
    selected_domain = st.selectbox("目标业务域", business_domains)
    uploaded_assets = st.file_uploader("上传 PDF/TXT", type=["pdf", "txt"], accept_multiple_files=True)

    # 【容错性锁定】：使用 2026 强制标准参数 width='stretch'
    if st.button("同步至认知空间", type="primary", width='stretch'):
        if uploaded_assets:
            save_path = os.path.join(settings.DATA_UPLOAD_DIR, selected_domain)
            os.makedirs(save_path, exist_ok=True)
            for asset in uploaded_assets:
                with open(os.path.join(save_path, asset.name), "wb") as f:
                    f.write(asset.getbuffer())
            st.success("✅ 资产已集成")
            st.toast("🛰️ 哨兵感应完成")

    st.markdown("---")

    # 【容错性锁定】：按钮宽度全量适配，防止布局坍塌
    if st.button("🔄 强制执行全量索引审计", width='stretch'):
        with st.spinner("执行索引重构..."):
            st.session_state.knowledge_engine = initialize_knowledge_base(force_rebuild=True)
        st.toast("索引已重建")

    if st.button("🗑️ 清空交互上下文", width='stretch'):
        st.session_state.messages = []
        st.rerun()

# ==========================================
# 4. 主界面：智慧问答 (重点优化层)
# ==========================================
col_chat, col_history = st.columns([3, 2], gap="large")

with col_chat:
    st.title("🧩 智慧交互决策中心")
    st.caption(f"Architecture: RAG-based | Model: {settings.LLM_MODEL}")

    if "messages" not in st.session_state:
        st.session_state.messages = []

    # 渲染历史记录
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            # 【容错性锁定】：严格判断 sources 列表，只有当后端返回非空来源时才渲染 expander
            # 理由：防止在“闲聊拦截”或“拒绝回答”状态下出现空的视觉框
            if "sources" in message and message["sources"]:
                with st.expander("📚 参考来源"):
                    for s in message["sources"]: st.caption(f"📍 {s}")

    # 输入处理
    if prompt := st.chat_input("请键入业务指令..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            response_placeholder = st.empty()
            full_response = ""

            # 【前后端接口锁定】：
            # 此处统一解包为 (生成器, 来源列表)。
            # 容错：即使后端引擎因意图识别未触发检索，返回的 sources=[] 也能被下文完美兼容。
            stream_gen, sources = get_chat_response_stream(prompt)

            for chunk in stream_gen:
                full_response += chunk
                response_placeholder.markdown(full_response + "▌")
            response_placeholder.markdown(full_response)

            # 【视觉容错逻辑】：
            # 只有当 sources 确实包含数据（即真实触发了知识库检索）时才挂载溯源组件。
            # 这解决了“hello kitty”等闲聊场景下不会莫名其妙挂载一个保险文档来源的尴尬。
            if sources:
                with st.expander("🎓 认知溯源", expanded=True):
                    for src in sources: st.info(f"📄 来源资产：`{src}`")

        # 最终状态持久化
        st.session_state.messages.append({
            "role": "assistant",
            "content": full_response,
            "sources": sources
        })

# ==========================================
# 5. 右侧面板：资产审计看板
# ==========================================
with col_history:
    st.title("📊 知识资产审计")
    asset_history = []
    base_dir = settings.DATA_UPLOAD_DIR

    # 【容错性锁定】：增加路径存在性检查，防止初次运行目录未创建时报错
    if os.path.exists(base_dir):
        for root, _, files in os.walk(base_dir):
            for file in files:
                # 过滤掉系统临时文件，确保审计列表的纯净度
                if not file.startswith(('.', '~')):
                    f_path = os.path.join(root, file)
                    rel_path = os.path.relpath(root, base_dir)
                    asset_history.append({
                        "资产名称": file,
                        "业务维度": rel_path if rel_path != "." else "未分类资产",
                        "存储规模": f"{os.stat(f_path).st_size / 1024:.1f} KB",
                        "最近审计时间": datetime.fromtimestamp(os.stat(f_path).st_mtime).strftime("%Y-%m-%d %H:%M")
                    })

    # 【视觉兼容性锁定】：根据是否有资产动态切换显示内容
    if asset_history:
        # 2026 强制标准：width='stretch' 确保表格自适应布局
        df = pd.DataFrame(asset_history).sort_values(by="最近审计时间", ascending=False)
        st.dataframe(df, width='stretch', hide_index=True)
        st.divider()
        st.metric("集成资产总量", f"{len(asset_history)} Units")
    else:
        # 当目录为空或无文件时，提供友好的提示，而不是留白，增强用户引导
        st.info("📂 暂无资产集成记录。")