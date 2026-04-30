🛠️ Matrix Intelligence 项目代码开发与变更契约
**1. 环境与配置层 (Protocol & Config Layer)**
文件位置： app/config.py & .env

* **全量原则**：任何对 Settings 类的修改必须保持“全量输出”，禁止删除已有的核心参数（如 TOP_K, CHUNK_SIZE）。

* **物理安全防火墙**：为了防止 [WinError 10054] 错误，必须锁定以下本地化参数：

    LLM_NUM_CTX: 锁定为 4096（防止 Context 过长导致显存溢出）。

    LLM_TEMPERATURE: 统一引用 settings.LLM_TEMPERATURE（默认 0.1 确保严谨性）。

* **路径计算**：必须使用基于 BASE_DIR 的绝对路径计算，确保在不同终端路径下执行 streamlit run 均能准确定位 data/ 文件夹。

* **环境隔离**：.env 文件严禁推送到 Git，但必须在本地保持 “只读” (attrib +r .env) 以防被 Git 清理命令误删。

**2. 模型驱动层 (Models Layer)**
**文件位置**： app/models/llm.py

* **纯血本地化驱动**：严禁在代码中硬编码任何云端厂商（如 OpenAI）的默认逻辑。

* **单例模式**：llm 必须作为全局单例加载，防止多次初始化抢夺本地显存。

* **耐力协议**：

    必须显式设置 timeout=120，为本地模型推理留足缓冲时间。

    参数传递必须完全回溯至 settings 对象，严禁硬编码（如 temperature=0.7）。

**3.异常脱水协议 (Exception Handling)**
**文件位置**： 全局业务逻辑

    优雅降级：当发生物理层断开（10054）或 OOM（显存溢出）时，系统不得闪退。

    错误回传：异常必须被 yield 或 return 捕获，并转化为用户可感知的“逻辑链路震荡”提示，而非原始的 Python 堆栈报错。

**4. 检索增强规范 (RAG Logic)**
* **文件位置**： app/core/engine.py & ingest.py

    K值敏感性：TOP_K 必须受控。对于 1.5b/7b 等本地小模型，TOP_K 建议保持在 3 以平衡精度与显存负载。

    分块一致性：CHUNK_SIZE (400) 与 CHUNK_OVERLAP (80) 的修改必须同步触发 ingest.py 的重运行，确保向量库数据与配置同步。

**5. Git 与 IDE 协作规范**
    防丢机制：在 PyCharm 中取消 Hide Ignored Files 勾选，确保灰色的 .env 始终在视觉受控范围内。

    忽略清单：.gitignore 必须保护 data/ 目录和 .env，防止本地保密数据上传，但开发者需自备物理备份。

**6.模块独立性原则：**

    即使在项目其他地方已经导入过某个标准库（如 os, sys, time），在任何新文件中使用这些模块时，都必须在该文件头部重新 import。

    禁止跨文件“猜想”：不要假设 config.py 加载了 os，其他引用 settings 的文件就自动拥有了 os 的访问权。
**7.导入优化协议：**

    顶部导入 (Top-level)：仅限标准库（os, time）和核心配置（settings, logger）。

    局部导入 (Local import)：凡是涉及具体业务逻辑、且容易引发循环依赖的跨层调用（如 Service 调用 Pipeline），必须放在函数内部进行延迟导入（Lazy Import）。禁止在文件頂部直接 from app.pipeline.ingest import ...
**🛡️ 变更审计清单 (每次提交前自检)**
[ ] Settings 类中 TOP_K 还在吗？

[ ] LLM_TEMPERATURE 是否关联了配置文件？

[ ] .env 的物理文件是否还存在？

[ ] 路径计算是否依然基于 BASE_DIR 的绝对路径？


