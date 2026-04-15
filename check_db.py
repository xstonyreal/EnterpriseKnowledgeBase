from langchain_community.vectorstores import FAISS
from app.models.embeddings import embeddings
from app.config import settings
import os

# 1. 定位索引路径 (根据您 config.py 里的设置拼接)
db_path = os.path.join(settings.CHROMA_PERSIST_DIR, "faiss_index")

print(f"🔍 正在检查索引目录: {db_path}")

# 2. 检查文件夹是否存在
if not os.path.exists(db_path):
    print("❌ 索引文件夹不存在！请先运行 ingest.py")
else:
    # 3. 加载已存在的索引
    try:
        print("📚 正在加载本地 FAISS 索引...")
        db = FAISS.load_local(db_path, embeddings, allow_dangerous_deserialization=True)

        # 4. 获取文档总数
        count = db.index.ntotal
        print(f"✅ 索引加载成功！库中总共有 {count} 个片段。")

        # 5. 打印前 3 条内容看看
        print("\n--- 🧐 抽检前 3 条内容 ---")
        docs = db.similarity_search(query="太平洋保险", k=3)

        for i, doc in enumerate(docs):
            print(f"\n[片段 {i + 1}]:")
            print(doc.page_content)
            print("-" * 30)

    except Exception as e:
        print(f"❌ 加载失败: {e}")