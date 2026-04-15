🏢 企业私有化 AI 知识库助手 (Private-RAG-Assistant)
🌟 项目简介
本项目是一款专为个人及小微企业设计的本地化 AI 知识管理方案。通过结合 Local LLM (大语言模型) 与 RAG (检索增强生成) 技术，实现“数据不出本地，知识自动入库”的智能化体验。

核心价值
* 绝对隐私：所有计算与数据存储均在本地完成，无需连接公网，彻底杜绝企业敏感数据泄露风险。
* 零成本运行：针对无显卡的普通办公环境优化，支持在 CPU 上流畅运行轻量级模型。
* 自动化流水线：内置文件系统监听器，用户只需按目录归档文件，系统自动完成知识同步。

🛠️ 技术栈
* LLM 推理: Ollama (默认支持 Qwen2.5-0.5B / Llama3.2-1B)
* 向量检索: FAISS (Facebook AI Similarity Search)
* 开发框架: LangChain + FastAPI + Streamlit
* 文件监听: Watchdog (操作系统级文件感应)
* 嵌入模型: nomic-embed-text (本地化高性能向量模型)

📂 目录结构说明
```text
EnterpriseKnowledgeBase/
├── .env                  # 环境变量（API 密钥、模型名称、路径常量）
├── main.py               # 程序入口（启动 FastAPI 服务）
├── app.py                # 管理后台（Streamlit UI：上传、管理、对话）
├── data/                 # 数据持久化层
│   ├── uploads/          # 原始文档库（支持多级目录，如：行政、财务、技术）
│   └── vector_db/        # 向量数据库（index.faiss 存储地）
└── app/                  # 核心源代码
    ├── api/              # 接口层：定义 HTTP 路由与会话管理
    ├── core/             # 大脑层：RAG 执行逻辑、记忆管家、提示词管理
    ├── models/           # 模型层：封装 LLM 与 Embedding 对接逻辑
    ├── storage/          # 存储层：向量库加载与检索操作
    └── pipeline/         # 流水线：Loader 加载、增量入库、自动监听(Watcher)
```
🚀 快速上手指南
1.环境准备
* 操作系统: Windows 10/11
* 运行环境: Python 3.9+
* 核心依赖: 已安装 Ollama 并拉取模型：
   ollama pull qwen2.5:0.5b
   ollama pull nomic-embed-text
2.安装步骤
# 克隆/下载项目至本地
cd EnterpriseKnowledgeBase

# 创建并激活虚拟环境
python -m venv .venv
.venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt

3. 运行应用
你可以通过以下命令启动集成管理后台：
streamlit run app.py

💡 核心功能逻辑
📁 多目录管理
* 系统支持用户根据业务需求自定义 uploads/ 下的子目录（如：01_行政、02_财务）。
* 应用场景：不同部门的员工可以将文件放入对应的文件夹。
* 效果：系统会自动递归扫描所有子目录，保持物理路径与逻辑分类一致。

🔄 自动入库 (Auto-Ingest)
* 内置 Watcher.py 模块：
* 感知：当用户向 uploads 文件夹粘贴新文件或修改文件时，系统立即感应。
* 响应：后台自动触发 Ingest 逻辑，完成文件切片与向量库更新，无需人工干预。

🧠 记忆增强对话
通过 memory.py 模块记录 Session-ID，支持多轮对话上下文理解。即使用户在提问中使用代词（如“那这个政策怎么说？”），AI 也能结合前文准确回答。

⚠️ 部署建议
* 资源占用：由于采用 CPU 推理，建议在运行时关闭不必要的占用内存较高的程序。
* 文档质量：为了获得更好的回答效果，建议上传结构清晰的文本类文件（PDF、Word、TXT）。
* 安全提示：虽然数据不出本地，但建议对项目所在的 data/ 目录定期进行磁盘备份。


