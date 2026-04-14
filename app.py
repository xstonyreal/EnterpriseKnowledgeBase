import streamlit as st
import os
import time
import pandas as pd
import threading
from datetime import datetime

# 导入你现有的业务模块
from app.pipeline.watcher import start_watcher
from app.core.engine import get_chat_response
from app.config import settings
from app.pipeline.ingest import ingest_documents

# --- 1. 后台线程：启动哨兵 ---
# 使用 session_state 确保哨兵在 Streamlit 刷新时不会重复启动
if "watcher_started" not in st.session_state:
    thread = threading.Thread(target=start_watcher, daemon=True)
    thread.start()
    st.session_state.watcher_started = True

# --- 2. 页面配置 ---
st.set_page_config(
    page_title="企业知识库管理后台",
    page_icon="🏢",
    layout="wide"
)

# --- 3. 侧边栏：上传与分类 ---
with st.sidebar:
    st.header("📤 数据入库")

    # 定义部门/范围目录
    categories = ["通用", "财务部", "技术部", "行政部", "业务部"]
    selected_cat = st.selectbox("文件归属部门", categories)

    uploaded_files = st.file_uploader(
        "选择文档 (支持多选)",
        type=["pdf", "txt"],
        accept_multiple_files=True
    )

    if st.button("开始上传并同步", type="primary"):
        if uploaded_files:
            save_path = os.path.join(settings.DATA_UPLOAD_DIR, selected_cat)
            os.makedirs(save_path, exist_ok=True)

            progress_bar = st.progress(0)
            for i, file in enumerate(uploaded_files):
                full_path = os.path.join(save_path, file.name)
                with open(full_path, "wb") as f:
                    f.write(file.getbuffer())
                progress_bar.progress((i + 1) / len(uploaded_files))

            st.success(f"✅ 成功上传 {len(uploaded_files)} 个文件到 [{selected_cat}]")
            st.info("🛰️ 哨兵已感知变动，后台正在重新入库...")
        else:
            st.warning("请先选择要上传的文件")

    st.divider()
    if st.button("🔄 手动触发全量入库"):
        with st.spinner("正在强制更新索引..."):
            ingest_documents()
        st.toast("索引已手动刷新！")

# --- 4. 主界面布局 ---
col_chat, col_history = st.columns([3, 2])

with col_chat:
    st.title("💬 智能助手测试")
    st.caption(f"当前模型: {settings.LLM_MODEL} | 架构: FAISS + LCEL")

    # 聊天记录管理
    if "messages" not in st.session_state:
        st.session_state.messages = []

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if prompt := st.chat_input("输入问题测试知识库..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("正在检索本地资料..."):
                response = get_chat_response(prompt)
                st.markdown(response)
        st.session_state.messages.append({"role": "assistant", "content": response})

with col_history:
    st.title("📜 知识库文件概览")

    # 扫描物理目录生成历史表
    history_list = []
    base_dir = settings.DATA_UPLOAD_DIR

    if os.path.exists(base_dir):
        for root, dirs, files in os.walk(base_dir):
            for file in files:
                if not file.startswith(('.', '~')):  # 过滤系统文件
                    file_path = os.path.join(root, file)
                    rel_path = os.path.relpath(root, base_dir)
                    # 处理根目录显示
                    category = rel_path if rel_path != "." else "未分类"

                    file_stat = os.stat(file_path)
                    history_list.append({
                        "文件名": file,
                        "所属部门": category,
                        "大小": f"{file_stat.st_size / 1024:.1f} KB",
                        "最后更新": datetime.fromtimestamp(file_stat.st_mtime).strftime("%Y-%m-%d %H:%M")
                    })

    if history_list:
        df = pd.DataFrame(history_list)
        # 按更新时间倒序排列
        df = df.sort_values(by="最后更新", ascending=False)
        st.dataframe(df, use_container_width=True, hide_index=True)
        st.write(f"📊 库内共有 **{len(history_list)}** 份文档")
    else:
        st.info("📂 知识库目前是空的，请从左侧上传。")