"""
UI 日志捕获器
将日志实时展示到 Streamlit UI
"""

import streamlit as st
from typing import List
from datetime import datetime


def add_ui_log(message: str):
    """手动添加日志到 UI"""
    try:
        if "ui_logs" not in st.session_state:
            st.session_state.ui_logs = []

        timestamp = datetime.now().strftime("%H:%M:%S")
        st.session_state.ui_logs.append(f"{timestamp} | {message}")

        if len(st.session_state.ui_logs) > 100:
            st.session_state.ui_logs.pop(0)
    except Exception:
        pass


def clear_ui_logs():
    """清空 UI 日志"""
    if "ui_logs" in st.session_state:
        st.session_state.ui_logs = []


def get_ui_logs() -> List[str]:
    """获取当前 UI 日志列表"""
    return st.session_state.get("ui_logs", [])