# main.py
import os
import sys
from app.config import settings
from app.core.engine import get_chat_response

# --- [架构升级：引入服务层] ---
# 统一调用 Service，确保逻辑与网页版 100% 同步
from app.services.ingest_service import initialize_knowledge_base


def main():
    """
    企业知识库助手 - 命令行入口 (CLI Mode)
    基于工业级服务化架构，实现快速决策支持
    """
    print("========================================")
    print("🤖 Enterprise Intelligence - 核心指挥部")
    print(f"📡 引擎状态: 已就绪 | 架构: RAG-Neural")
    print(f"📂 资产目录: {settings.DATA_UPLOAD_DIR}")
    print("========================================\n")

    # ==========================================
    # 1. 核心治理：调用 Service 执行自省式启动
    # ==========================================
    # 逻辑：
    # - initialize_knowledge_base 会自动检测索引是否存在。
    # - 如果存在，执行“秒开”加载；如果不存在，执行“全量初始化”。
    # - force_rebuild=False 确保了它不会鲁莽地重复切片。
    try:
        print("🛠️  正在执行知识空间自省与挂载...")
        initialize_knowledge_base(force_rebuild=False)
        print("✅ 语义向量空间已成功映射至内存。")
    except Exception as e:
        print(f"❌ 空间初始化失败: {e}")
        sys.exit(1)

    # ==========================================
    # 2. 交互循环
    # ==========================================
    print("\n💬 业务指令中心已开启 (输入 'exit' 退出):")
    print("提示：系统已进入 Metadata 增强模式，具备事实溯源能力。")

    while True:
        try:
            user_input = input("\n👤 业务指令 > ")

            # 退出指令处理
            if user_input.lower() in ['exit', 'quit', '退出', 'bye']:
                print("\n👋 系统休眠。感谢使用 Matrix Intelligence。")
                break

            # 空输入处理
            if not user_input.strip():
                continue

            # 执行 RAG 认知合成
            print("🧠 正在检索关联语义簇并合成响应...")
            answer = get_chat_response(user_input)

            # 输出结果
            print("-" * 40)
            print(f"🤖 决策建议: \n{answer}")
            print("-" * 40)

        except KeyboardInterrupt:
            print("\n\n⚠️  强制退出。")
            break
        except Exception as e:
            print(f"❌ 认知合成异常: {e}")


if __name__ == "__main__":
    # 确保根目录在 Python 路径中，避免导入错误
    root_path = os.path.dirname(os.path.abspath(__file__))
    if root_path not in sys.path:
        sys.path.append(root_path)

    main()