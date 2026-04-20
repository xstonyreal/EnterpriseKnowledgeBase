# main.py
import os
import sys
from app.config import settings
from app.core.engine import get_chat_response
from app.core.logger import logger

# --- [架构升级：引入服务层] ---
# 统一调用 Service，确保逻辑与网页版 100% 同步
from app.services.ingest_service import initialize_knowledge_base


def main():
    """
    Matrix Intelligence - 核心指挥部 (CLI Mode)
    基于分域隔离架构，实现全本地化 RAG 决策支持
    """
    # 清屏美化（可选）
    # os.system('cls' if os.name == 'nt' else 'clear')

    print("==================================================")
    print(f"🧬 {settings.PROJECT_NAME} - 核心指挥部")
    print(f"📡 架构版本: RAG-Matrix v1.0 | 状态: 生产就绪")
    print(f"📂 知识域目录: {settings.DATA_UPLOAD_DIR}")
    print("==================================================\n")

    # ==========================================
    # 1. 核心治理：底座初始化 (感知注入)
    # ==========================================
    # 逻辑依据：
    # - 调用 initialize_knowledge_base 执行自省。
    # - 优先热加载本地 FAISS 资产，无资产时自动启动多线程 Ingest。
    try:
        print("🛠️  正在执行知识空间自省与挂载...")
        vectorstore = initialize_knowledge_base(force_rebuild=False)

        if vectorstore is None:
            print("⚠️  [底座预警] 当前知识空间为空。")
            print(f"💡 请将保险业务文档放入: {settings.DATA_UPLOAD_DIR} 并重启系统。")
            # CLI 模式下，空资产通常不退出，允许用户通过对话触发报错或空检索
        else:
            print("✅ 语义向量空间已成功映射至内存 (Matrix Ready)。")

    except Exception as e:
        print(f"🚨 空间初始化失败: {e}")
        logger.critical(f"系统启动中断: {str(e)}")
        sys.exit(1)

    # ==========================================
    # 2. 指令交互循环 (RAG Loop)
    # ==========================================
    print("\n💬 业务指令中心已开启 (输入 'exit' 退出):")
    print(f"提示：系统运行于 {settings.LLM_MODEL} 引擎，具备分域隔离检索能力。")

    while True:
        try:
            # 模拟交互终端
            user_input = input("\n👤 业务指令 > ").strip()

            # 1. 退出指令处理
            if user_input.lower() in ['exit', 'quit', '退出', 'bye']:
                print("\n👋 正在释放内存资产... 系统休眠。")
                break

            # 2. 空输入拦截
            if not user_input:
                continue

            # 3. 执行 RAG 认知合成
            # get_chat_response 内部会调用封装好的检索链
            print("🧠 正在检索关联语义簇并合成决策建议...")
            answer = get_chat_response(user_input)

            # 4. 响应输出
            print("-" * 50)
            print(f"🤖 Matrix 决策建议: \n{answer}")
            print("-" * 50)

        except KeyboardInterrupt:
            print("\n\n⚠️  检测到强制中断，系统安全停机。")
            break
        except Exception as e:
            print(f"❌ 认知合成异常: {e}")
            logger.error(f"对话异常: {str(e)}")


if __name__ == "__main__":
    # 环境自检：确保项目根目录在系统路径中，根治导入报错
    root_path = os.path.dirname(os.path.abspath(__file__))
    if root_path not in sys.path:
        sys.path.append(root_path)

    # 启动 Matrix 底座
    main()