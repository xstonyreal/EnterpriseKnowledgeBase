🏢 **Matrix Intelligence: 企业级分域隔离 RAG 智能底座**

[![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)](https://www.python.org/)
[![LangChain](https://img.shields.io/badge/LangChain-1.2+-green.svg)](https://www.langchain.com/)
[![Streamlit](https://img.shields.io/badge/Streamlit-2026-red.svg)](https://streamlit.io/)
[![Ollama](https://img.shields.io/badge/Ollama-0.6+-orange.svg)](https://ollama.ai/)

🌟## 📌 项目简介

本项目一款专为保险、合规及金融等高数据敏感行业设计的 **RAG（检索增强生成）系统**。它摒弃了市面上主流 RAG 应用的“黑盒模式”，通过**物理级隔离**与**动态感知架构**，实现了从数据入库到决策产出的**全链路可追溯**与**高度安全**。

### 核心价值

- 🔒 **绝对隐私**：所有计算与数据存储均在本地完成，无需连接公网，彻底杜绝企业敏感数据泄露风险。
- 💰 **零成本运行**：针对无显卡的普通办公环境优化，支持在 CPU 上流畅运行轻量级模型。
- ⚡ **自动化流水线**：内置文件系统监听器，用户只需按目录归档文件，系统自动完成知识同步。

---

## 🏗️ 架构愿景：五层金字塔设计哲学

本项目在代码设计上采用了高度解耦的五层架构，将复杂逻辑封装为独立 Service，具备极强的水平扩展能力：

| 层级 | 文件位置 | 设计理念 | 核心功能 |
|------|----------|----------|----------|
| **协议与环境层** | `app/config.py` + `.env` | 系统的“物理常数”与安全边界 | 统一管理存储路径、模型参数、Chunk 尺寸规范、异常处理协议 |
| **感知层** | `services/watcher_service.py` | 建立“活体化”知识库 | 内置 Sentinel（哨兵）机制，毫秒级感应物理磁盘变动 |
| **流水线层** | `pipeline/ingest.py` + `services/ingest_service.py` | 切片的“微米级”手术与计算负载均衡 | 400-1200 字符动态窗口及 15% 语义重叠，并发分批处理 |
| **内核层** | `core/engine.py` | 物理级的“认知域隔离” | 核心 RAG 引擎，强制注入 Domain 标签过滤 |
| **交互层** | `app_ui.py` | 2026 标准下的“冷热隔离”契约化交互 | 物理预检拦截器，资产审计看板，像素级溯源 |

---

## ✨ 核心诱人品质

- 🚀 **动态感应同步**：管理员只需管理文件夹，剩下的交给哨兵。零维护成本，即存即用。
- 🧼 **洁净重塑能力**：支持一键触发“认知大清洗”，确保检索空间的绝对纯净与审计一致性。
- 🔒 **物理安全契约**：将业务域直接映射为磁盘子目录。这种“物理即权限”的设计，是对企业数据主权最硬核的保护。
- 🔍 **混合检索引擎**：向量检索（FAISS）+ 关键词检索（BM25）+ RRF 融合
- 🎓 **极速决策洞察**：管理层通过“全域视图”可瞬间发现跨部门政策冲突，将沉睡的文档转化为流动的管理红利。

---

## 🧩 设计理念

- **入口分化，场景对齐**：区分命令行/API 生产端与 Streamlit 智慧交互端，满足自动化集成与人工调度的双重需求。
- **认知溯源，拒绝幻觉**：引入多级意图识别逻辑。系统能分清“业务咨询”与“通用寒暄”，在无法通过本地库找到答案时，利用 LLM 通用常识进行专业引导，而非盲目拒绝。
- **服务化架构**：将数据流水线 (Pipeline) 与业务逻辑 (Services) 深度解耦，支持更复杂的增量入库与目录监听任务。

---

## 🛡️ Matrix Intelligence 核心安全规范

### 1. 逻辑安全：异常脱水协议 (Exception Dehydration)

- **所在层级**：全层级（主要在 Core 与 Pipeline）
- **规范内容**：禁止生成器或延迟任务直接引用原始异常对象 e
- **工程目的**：规避 NameError。通过“捕获即快照”，确保在长链路、流式输出中，错误信息永远是线程安全且生命周期完整的

### 2. 数据安全：物理域隔离 (Physical Domain Isolation)

- **所在层级**：Core（内核层）
- **规范内容**：强制在向量检索时注入 `filter={'domain': selected_domain}`
- **工程目的**：确保 AI 的认知被物理文件夹边界锁死

### 3. 负载安全：分批吞吐限流 (Batch Load Control)

- **所在层级**：Pipeline（流水线层）
- **规范内容**：设定 BATCH_SIZE 阈值，禁止全量数据一次性冲击显存/内存
- **工程目的**：防止因资产过大导致系统 OOM（内存溢出）或死机

### 4. 交互安全：冷热隔离拦截 (Pre-flight Interception)

- **所在层级**：Presentation（交互层）
- **规范内容**：启动时执行“物理预检”，若无索引则强制保持 None
- **工程目的**：防止系统在未授权的情况下自动执行高能耗任务

### 5. 状态安全：单例模式锁定 (Singleton Enforcement)

- **所在层级**：Service（服务调度）
- **规范内容**：通过 `_CACHED_VECTORSTORE` 全局变量锁定唯一内存实例
- **工程目的**：防止 Streamlit 的 Rerun 机制导致重复加载模型和索引

---

## 🛠️ 技术栈

| 组件 | 技术选型 |
|------|----------|
| LLM 推理 | Ollama（默认 Qwen2.5-1.5B / Llama3.2-1B） |
| 向量引擎 | FAISS（本地持久化索引）+ BM25 混合检索 |
| 融合算法 | RRF（Reciprocal Rank Fusion） |
| 开发框架 | LangChain + FastAPI（异步 API）+ Streamlit 2026 |
| 文件监听 | Watchdog（操作系统级文件感应） |
| 嵌入模型 | nomic-embed-text（本地化高性能向量模型） |

---

📂 目录结构说明
```text
EnterpriseKnowledgeBase/
├── .env                     # 【核心配置】隔离敏感信息（API Key/模型版本/数据库地址）
├── .gitignore               # 【资产过滤】防止将缓存、索引及虚拟环境推送到 Git
├── plan.md                  # 【研发路线】记录 Sprint 计划、待办事项 (Backlog) 与 Bug 修复进度
├── Architecture Contract.md  # 【开发规约】约束代码风格、层级调用逻辑与模块职责边界
├── main.py                  # 【入口 A】后端 CLI 交互中心，用于本地测试与维护
├── app_ui.py                # 【入口 B】Streamlit 全栈 UI，2026 风格业务操作台
├── requirements.txt         # 【环境依赖】项目运行所需的 Python 库锁本
│
├── data/                    # 【数据资产层】
│   ├── uploads/             # [输入] 原始业务文档，支持按部门/业务线创建子文件夹
│   └── vector_db/           # [输出] 持久化 FAISS 语义索引，支持“秒级加载”
│
└── app/                     # 【逻辑心脏层】
    ├── __init__.py          # 模块导出声明
    ├── config.py            # 全局配置单例：基于 Pydantic 的类型安全配置管理
    │
    ├── api/                 # 【接口层】基于 FastAPI 的分布式扩展预留
    │   ├── chat.py          # 对话状态管理、会话持久化逻辑
    │   └── endpoints.py     # 外部 API 路由分发中心
    │
    ├── core/                # 【引擎层】RAG 系统的核心大脑
    │   ├── engine.py        # 调度核心：负责检索、上下文组装与 LLM 推理联动
    │   ├── logger.py        # 审计系统：全局结构化日志记录与错误追踪
    │   └── prompts.py       # 提示词库：多场景保险业务专家级 Prompt 模板
    │
    ├── models/              # 【模型层】异构计算适配
    │   ├── llm.py           # 本地认知引擎封装 (Ollama/Qwen)
    │   └── embeddings.py    # 向量化模型封装 (Nomic/HuggingFace)
    │
    ├── pipeline/            # 【流水线层】非结构化数据治理
    │   ├── ingest.py        # 数据分片 (Chunking) 与向量入库核心原子操作
    │   ├── loader.py        # 多模态适配器：PDF、Word、TXT、Markdown 的解析读取
    │   └── watcher.py       # 文件探测逻辑：获取目录结构、元数据提取
    │
    ├── services/            # 【服务层】业务逻辑聚合
    │   ├── ingest_service.py # 调度中枢：处理重构、并发入库与单例生命周期管理
    │   ├── watcher_service.py# 异步服务：目录变更的监听与热挂载调度
    │   └── search_service.py # 混合检索引擎（FAISS + BM25 + RRF）    
    │
    ├── storage/             # 【存储适配层】
    │   └── vector_db.py     # 向量数据库驱动：执行语义搜索与 Metadata 过滤
    │
    └── utils/               # 【工具集】通用逻辑复用
        └── __init__.py      # 文件哈希、时间转换等独立工具函数

```
提示：详细的开发规范请参考项目根目录下的 [Architecture Contract.md]

## 🚀 快速上手指南

### 1. 环境准备

- **操作系统**：Windows 10/11 / macOS / Linux
- **运行环境**：Python 3.9+
- **核心依赖**：已安装 Ollama 并拉取模型

```bash
ollama pull qwen2.5:1.5b
ollama pull nomic-embed-text

****2.安装步骤****

# 克隆/下载项目至本地
cd EnterpriseKnowledgeBase

# 创建并激活虚拟环境（推荐）
python -m venv .venv
source .venv/bin/activate      # Linux/macOS
.venv\Scripts\activate         # Windows

# 安装依赖
pip install -r requirements.txt

****3. 运行应用****

# 启动 Streamlit 全栈 UI（推荐）
streamlit run app_ui.py

# 或使用 CLI 命令行模式
python main.py

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

⚠️ 维护建议
* 索引清理: 若目录结构发生大幅度调整，建议点击侧边栏的“强制全量索引审计”进行重构。
* 资源监控: 建议在 CPU 推理模式下，文档切片长度保持在 500-1000 tokens 以平衡检索精度与性能。

💡 核心治理逻辑更新(Updated by 20260416)

🔄 动态流水线 (Services):
项目不再是单一脚本运行，而是通过 watcher_service 长期驻留后台。每当向 uploads/ 拖入文件，ingest_service 会立即进行“认知对齐”，实现无感知的知识库更新。

🧠 智商平衡 Prompt:
针对 RAG 常见的“强行关联”问题，内置了情商过滤层。当用户输入“Hello”或通用常识（如“航空险建议”）时，AI 将结合自身模型知识进行礼貌响应；当涉及核心业务时，则触发深度文档溯源。

📊 认知溯源 UI:
全量适配 Streamlit 2026 标准。只有当 AI 真正参考了本地文件时，才会渲染“认知溯源”卡片，确保交互界面的整洁与专业感。

📈 商业演进路线

Phase 1 (Current): 手动档分域隔离，满足部门级精准应用。

Phase 2: 接入 RBAC 身份识别 Service，实现“人岗匹配”的自动权限过滤。

Phase 3: 开启多模态审计 Service，支持视频及语音资产的合规检索。


📝 更新日志
2026-04-30
✅ 完成全部核心模块代码审阅

✅ 统一异常脱水平台（exceptions.py）

✅ 实现混合检索引擎（FAISS + BM25 + RRF）

✅ 完善哨兵监控与服务层架构

✅ 修复配置文件路径计算逻辑

✅ Streamlit UI 冷热启动拦截器

📄 许可证
内部项目，仅供企业授权用户使用。

Matrix Intelligence - 让每一份文档都成为可审计的管理红利