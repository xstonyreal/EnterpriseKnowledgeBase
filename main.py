# main.py
import os
import sys
import argparse
from app.config import settings
from app.core.engine import get_chat_response_stream
from app.core.logger import logger
from app.services.ingest_service import initialize_knowledge_base
from app.services.watcher_service import start_sentinel


def print_banner():
    """打印啟動橫幅"""
    print("=" * 60)
    print(f"🧬 {settings.PROJECT_NAME} - 企業級分域隔離 RAG 底座")
    print(f"📡 版本: 1.0 | 狀態: 生產就緒")
    print(f"📂 知識域目錄: {settings.DATA_UPLOAD_DIR}")
    print(f"🤖 認知引擎: {settings.LLM_MODEL}")
    print("=" * 60)
    print()


def cmd_reindex():
    """手動重建索引（--reindex）"""
    print("\n🔄 正在執行全量索引重建...")
    print("⚠️  此操作將清空現有向量庫並重新處理所有文檔\n")

    try:
        vectorstore = initialize_knowledge_base(force_rebuild=True)
        if vectorstore:
            print("\n✅ 索引重建完成！")
        else:
            print("\n⚠️  重建完成，但未發現有效文檔")
    except Exception as e:
        print(f"\n❌ 重建失敗: {e}")
        logger.error(f"重建失敗: {str(e)}")
        sys.exit(1)


def cmd_chat():
    """啟動 CLI 對話模式"""
    print_banner()

    # 初始化知識底座
    print("🛠️  正在執行知識空間自省與掛載...")
    try:
        vectorstore = initialize_knowledge_base(force_rebuild=False, check_manifest=True)

        if vectorstore is None:
            print("⚠️  [底座預警] 當前知識空間為空。")
            print(f"💡 請將文檔放入: {settings.DATA_UPLOAD_DIR}")
            print("   或執行 `python main.py --reindex` 手動重建索引\n")
        else:
            print("✅ 語義向量空間已成功映射至內存\n")

        # 啟動哨兵（後臺監控）
        start_sentinel()
        print("📡 哨兵已啟動，正在監控文件變動\n")

    except Exception as e:
        print(f"🚨 空間初始化失敗: {e}")
        logger.critical(f"系統啟動中斷: {str(e)}")
        sys.exit(1)

    # 對話循環
    print("💬 業務指令中心已開啟 (輸入 'exit' 退出):")
    print(f"📌 提示：輸入 'domain:財務部 問題' 可指定業務域查詢\n")

    while True:
        try:
            user_input = input("\n👤 業務指令 > ").strip()

            if user_input.lower() in ['exit', 'quit', '退出', 'bye']:
                print("\n👋 正在釋放資源... 系統休眠。")
                break

            if not user_input:
                continue

            # 解析可選的域前綴
            filter_domain = None
            query_text = user_input

            if user_input.startswith("domain:"):
                parts = user_input.split(" ", 1)
                if len(parts) == 2:
                    domain_part = parts[0].replace("domain:", "")
                    filter_domain = domain_part
                    query_text = parts[1]
                    print(f"🎯 檢索域: {filter_domain}")

            print("🧠 正在檢索並合成決策建議...")

            stream_gen, sources = get_chat_response_stream(query_text, filter_domain=filter_domain)

            print("-" * 50)
            full_response = ""
            for chunk in stream_gen:
                full_response += chunk
                print(chunk, end="", flush=True)
            print("\n" + "-" * 50)

            # 顯示溯源信息
            if sources:
                print("\n📚 參考來源:")
                for idx, s in enumerate(sources[:3]):
                    src = s.get("source", "未知") if isinstance(s, dict) else s
                    score = s.get("score", 0) if isinstance(s, dict) else 0
                    print(f"   {idx + 1}. {os.path.basename(src)} (匹配度: {score:.2f})")
                print()

        except KeyboardInterrupt:
            print("\n\n⚠️  檢測到強制中斷，系統安全停機。")
            break
        except Exception as e:
            print(f"❌ 認知合成異常: {e}")
            logger.error(f"對話異常: {str(e)}")


def main():
    """主入口"""
    parser = argparse.ArgumentParser(description="Matrix Intelligence CLI")
    parser.add_argument("--reindex", action="store_true", help="手動全量重建索引")
    parser.add_argument("--chat", action="store_true", help="啟動對話模式")

    args = parser.parse_args()

    # 確保項目根目錄在路徑中
    root_path = os.path.dirname(os.path.abspath(__file__))
    if root_path not in sys.path:
        sys.path.append(root_path)

    if args.reindex:
        cmd_reindex()
    else:
        cmd_chat()


if __name__ == "__main__":
    main()