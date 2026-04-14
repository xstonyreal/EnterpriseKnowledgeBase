# main.py
import os
import sys
from app.config import settings
from app.pipeline.ingest import ingest_documents
from app.core.engine import get_chat_response

print(f"--- 当前 Python 路径: {sys.executable} ---")
print(f"--- 已安装包搜索路径: {sys.path} ---")

def main():
    print("🤖 企业知识库助手 (FAISS版) 已启动")
    print(f"📂 数据目录: {settings.DATA_UPLOAD_DIR}")

    # 首次启动检查：如果数据库为空，自动执行入库
    # 直接使用 settings 里计算好的绝对路径
    db_path = settings.CHROMA_PERSIST_DIR


    if not os.path.exists(db_path):
        print("\n⏳ 检测到索引不存在，正在初始化数据...")
        ingest_documents()

    print("\n💬 请输入问题开始提问 (输入 'exit' 退出):")

    while True:
        user_input = input("\n👤 我: ")
        if user_input.lower() in ['exit', 'quit', '退出']:
            print("👋 再见！")
            break

        if not user_input.strip():
            continue

        try:
            answer = get_chat_response(user_input)
            print(f"🤖 助手: {answer}")
        except Exception as e:
            print(f"❌ 发生错误: {e}")


if __name__ == "__main__":
    main()