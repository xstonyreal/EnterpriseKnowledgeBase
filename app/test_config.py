# test_config.py
from app.config import settings

try:
    print(f"✅ 項目名稱: {settings.PROJECT_NAME}")
    print(f"✅ 上傳目錄: {settings.DATA_UPLOAD_DIR.absolute()}")
    print("🚀 配置預檢通過！")
except Exception as e:
    print(f"❌ 配置有誤: {e}")