# 模拟面试系统架构与实现详解

## 一、55 道核心面试题与参考答案

### 1. 系统架构与设计

**Q1：为什么要设计三层架构（交互层/编排层/基础层）？各层职责是什么？**
> **A：** 核心目的是**解耦与可扩展**。交互层负责协议适配（CLI/WebSocket/REST），无业务逻辑；编排层承载核心业务流程（Agent协作、记忆读写、Skill调度）；基础层提供原子AI能力（LLM推理、向量检索、数据库存储）。换一个大模型只需改基础层配置，新增Agent只需在编排层注册，前端接入只需对接交互层接口。

**Q2：意图路由器（Intent Router）是如何设计的？如何区分面试、技能练习还是闲聊？**
> **A：** 采用**LLM Few-Shot分类 + 规则兜底**的混合策略。Router Agent接收用户输入后，输出结构化意图标签（`interview`/`skill`/`chat`）及置信度。高置信度直接分流；低置信度触发澄清追问。规则兜底用于明显关键词（如“开始面试”直接命中）。

**Q3：为什么选择 LangGraph 而非简单的 Chain 或单 Agent Prompt？**
> **A：** 模拟面试是**有状态、多分支、可循环**的复杂流程：存在“出题→提问→追问→评估”的循环，以及“正常答题/要求提示/中途退出”的条件分支。LangGraph 的图结构支持循环边（cycle）、条件边（conditional edge）和持久化状态（checkpoint），天然适合多 Agent 协作与断点续传，而 Chain 是线性无状态的。

**Q4：如何保证 8 个 Agent 之间的数据传递与状态一致性？**
> **A：** 所有 Agent 共享一个**全局 State 对象**（TypedDict），明确定义字段如 `jd_info`、`resume_gap`、`current_question`、`evaluations`。每个 Agent 只读写自己职责相关的字段，通过 LangGraph 的 checkpointer 将 State 持久化到 Redis/Postgres，确保任意步骤崩溃后可恢复。

**Q5：项目中如何处理多会话并发隔离？**
> **A：** 每个用户会话分配唯一的 `session_id` 与 LangGraph `thread_id`。短期记忆（Redis）和长期记忆（MySQL）的 Key 均带 `session_id` 或 `user_id` 前缀；Weaviate 检索通过 metadata filter 隔离用户私有数据，防止会话间状态串扰。

**Q6：若后续需支持视频简历解析，现有架构如何扩展？**
> **A：** 利用三层架构横向扩展：基础层引入多模态模型（如 Qwen-VL）处理视频帧与 OCR；编排层新增 `VideoParseAgent`，负责抽取视频中的项目经历与技术关键词；交互层增加视频上传接口。其余出题、面试链路无需改动。

---

### 2. Agent 编排与 LangGraph

**Q7：LangGraph 中的 StateGraph 是什么？本项目如何定义 State？**
> **A：** StateGraph 是有向状态图，**节点是函数/Agent，边是流转规则**。本项目 State 定义为 TypedDict，包含：`jd: JDInfo`、`resume: ResumeInfo`、`questions: List[Question]`、`current_idx: int`、`chat_history: List[Message]`、`difficulty: Literal["easy","medium","hard"]`、`evaluations: List[Eval]`、`memory: UserProfile`。

**Q8：面试官 Agent 如何实现“根据回答实时追问深挖”？**
> **A：** 面试官节点内部包含**评估子模块**（轻量级 LLM 判断）。用户回答后，先判断完整性：若回答肤浅（如只答出概念），通过条件边触发**同题追问**（`follow_up` 计数 +1）；若回答错误，触发**降维提示**；若回答优秀，条件边流转至下一题。追问深度通过 `max_follow_up=2` 限制，防止死循环。

**Q9：LangGraph 的 conditional edge 在本项目中的具体应用场景？**
> **A：** 典型场景有三：① 出题规划后，若题库覆盖不足，走 `generate_new_question` 边；② 评估 Agent 后，若存在高频薄弱点，走 `review_plan` 边；③ 面试官节点后，若用户说“请解释考点”，走 `knowledge_skill` 边进入 Skill 子图，而非下一题。

**Q10：如何防止 Agent 间循环调用（如面试官与评估无限循环）？**
> **A：** 三层防护：① **业务逻辑限制**：评估节点标记 `evaluated=True`，条件边判断已评估则不再进入；② **轮次上限**：State 中维护 `turn_count`，超阈值强制结束面试；③ **LangGraph 兜底**：设置 `recursion_limit`，防止图执行无限递归。

**Q11：出题规划 Agent 如何结合 JD + 简历 + RAG 结果生成题目？**
> **A：** 执行**Gap Analysis**：JD 要求的技术栈与职级作为“目标态”，简历提取的技能作为“现状”，差集即为考察重点（如 JD 要求 Kafka 但简历未提）。RAG 检索对应差集的技术题库，LLM 根据 Gap 优先级与题目难度配额（基础 40%/进阶 40%/挑战 20%）生成最终题单。

**Q12：为什么面试官 Agent 要独立于出题规划 Agent？合并会有什么问题？**
> **A：** 遵循**单一职责原则**。出题规划关注“考什么”（战略层，决定考点分布），面试官关注“怎么问”（战术层，决定措辞、追问、互动）。合并会导致 Prompt 臃肿（>4k tokens），状态混乱，且面试官无法被 Skill 系统单独复用。

**Q13：评估 Agent 的打分维度如何设计？如何做到“每题即时评分”？**
> **A：** 维度采用**结构化 JSON**：`technical_accuracy`（技术正确性，40%）、`completeness`（要点覆盖度，30%）、`communication`（表达清晰度，30%）。即时评分通过异步非阻塞实现：用户回答提交后，评估 Agent 作为独立节点并行执行，结果写入 State 并即时推送给前端。

**Q14：如何在 LangGraph 中实现人机协同（Human-in-the-loop）？**
> **A：** 在关键节点（如评估报告生成后）插入 `interrupt`。图执行暂停，等待用户输入（如“重新评估”或“确认报告”），用户确认后通过 `Command.RESUME` 继续流转至复习规划 Agent。适用于需要人工确认的高风险决策环节。

---

### 3. RAG 检索与 LlamaIndex

**Q15：为什么选择 LlamaIndex 而不是直接操作向量库？**
> **A：** LlamaIndex 提供**高阶 RAG 抽象**：Index、Retriever、QueryEngine、PostProcessor、Reranker。可直接编排多路召回、融合、精排流程，无需手写大量胶水代码。直接操作向量库（如 Weaviate 原生 API）需自行处理文档切分、嵌入、重排，工程复杂度高。

**Q16：向量检索 + BM25 双路召回的具体实现方式？如何融合？**
> **A：** LlamaIndex 中分别构建 `VectorIndex`（Weaviate + text-embedding-v3）和 `KeywordIndex`（BM25Retriever）。同一 Query 并行检索，得到两个候选列表。使用 **RRF（Reciprocal Rank Fusion）** 融合：`score = Σ 1/(k + rank)`，k 常取 60，去重后取 TopK。兼顾语义泛化与关键词精准。

**Q17：为什么需要 LLM Rerank？RRF 融合后不是已经有结果了吗？**
> **A：** RRF 是**位置融合算法**，只考虑文档在各路中的排序位置，不理解内容语义。LLM Rerank（如 RankGPT 或 LLM-as-a-Judge）能深度分析 Query 与 Document 的细粒度相关性，识别伪相关文档（如标题匹配但内容不符），实现第二重语义过滤。

**Q18：text-embedding-v3 的向量维度与选型理由？**
> **A：** 通义 text-embedding-v3 通常为 **1024 或 1536 维**。选型理由：① 中文语义理解能力强；② 支持指令式嵌入（对 Query 和 Document 分别加前缀如 `representation: query`），提升非对称检索效果；③ 在中文技术八股文和面试题上效果优于通用模型。

**Q19：Weaviate 在本项目中的角色？为什么选择它？**
> **A：** Weaviate 作为**向量数据库**，存储面试题、答案、知识片段的向量表示。选择原因：① 原生支持混合检索（向量 + BM25）；② 提供 GraphQL 接口，查询灵活；③ Schema 可动态扩展；④ 支持本地无 Docker 部署（embedded 模式或二进制），符合本项目单用户本地场景。

**Q20：RAG 评估的三维指标 Faithfulness / Relevance / Completeness 如何定义？**
> **A：** `Faithfulness`：生成内容是否基于检索上下文，有无幻觉（通过 NLI 模型或 LLM 判断）；`Relevance`：检索文档与 Query 的相关程度（LLM 打分 1-5）；`Completeness`：答案是否覆盖 Query 的所有子要点。通过 LLM-as-a-Judge 自动化评估，人工抽检校准。

**Q21：TopK 调优实验是怎么做的？结论是什么？**
> **A：** 构建黄金测试集（50 组 JD+期望考点），分别实验 TopK=3/5/8/10/15。评估指标为召回题目的 `Recall@K` 与 `MRR`。实验结论：本项目在 **TopK=5** 时，经 RRF+LLM Rerank 后的 F1 最高；TopK>8 引入噪声，导致 Rerank 负担加重且准确率下降。

**Q22：如果题库中没有直接匹配的题目，如何处理？**
> **A：** 采用 **RAG + 动态生成** 混合策略：检索 Top3 相似题目作为 Few-shot 示例，Prompt 中约束 LLM 基于 JD 要求与参考示例生成新题。新题标记为 `generated` 不入正式库，经人工审核后可沉淀为资产，形成题库飞轮。

**Q23：如何保证 RAG 检索结果不泄露敏感或私有题目？**
> **A：** 三层防护：① **Metadata 过滤**：检索时强制过滤 `is_public=true`；② **数据脱敏**：入库前替换公司名、人名；③ **权限隔离**：Weaviate 按用户 ID 做命名空间隔离（或在查询时加入 `user_id` filter）。本地部署也避免了第三方云服务商的数据泄露风险。

---

### 4. 记忆系统

**Q24：短期记忆和长期记忆的分界逻辑是什么？为什么需要两种存储？**
> **A：** 分界以**会话生命周期**为界。短期记忆是当前面试的上下文（最近 5 轮对话、当前题目状态），用 Redis（TTL 24h）支持高并发读写；长期记忆是跨会话的用户画像与薄弱点，用 MySQL 持久化。Redis 快但易失，MySQL 可靠但慢，二者互补。

**Q25：Redis 中如何存储短期记忆？数据结构是什么？**
> **A：** 采用 Redis **Hash** 结构，Key 为 `interview:session:{session_id}`，Field 存储 `state_json`（序列化后的 State 子集）。设置 `EX 86400` 自动过期。也可使用 RedisJSON 模块支持复杂查询，但 Hash 足够轻量。

**Q26：MySQL 的长期记忆表结构如何设计？**
> **A：** 核心三张表：`users`（user_id, profile_json）；`interview_sessions`（session_id, user_id, jd_summary, total_score, created_at）；`weakness_tags`（user_id, skill_tag, gap_desc, frequency, last_encounter）；`question_performance`（question_id, user_id, score, answer_summary）。通过 `user_id` 关联，支持薄弱点的时间序列分析。

**Q27：下次面试时如何加载长期记忆影响出题？**
> **A：** 面试初始化阶段，**出题规划 Agent** 查询 MySQL，按 `frequency DESC` 取出 Top5 薄弱标签（如“Redis 集群模式不熟”）。在 Prompt 中注入指令：“该用户历史薄弱点为 [X]，请在题单中提高 X 的权重，并由面试官重点追问”。实现千人千面的考察策略。

**Q28：记忆系统如何防止“记忆污染”（如把错误回答当正确记忆）？**
> **A：** 写入长期记忆前需**评估过滤**：仅当评估 Agent 确认“用户回答错误/不完整”时，才将对应技能点写入 `weakness_tags`；正确回答不生成薄弱点。定期（如每月）由总结 Agent 对零散记忆做摘要，消除噪声与冗余。

---

### 5. MCP 协议与工具集成

**Q29：什么是 MCP（Model Context Protocol）？相比传统 Function Calling 有什么优势？**
> **A：** MCP 是 Anthropic 提出的**开放标准协议**，标准化 AI 模型与外部工具/数据源的连接方式。相比传统 Function Calling（各平台 API 格式不一，耦合严重），MCP 的优势在于：① **一次接入，多端使用**；② 支持工具自动发现（Server 暴露工具列表）；③ 支持资源订阅与双向通信；④ 解耦工具提供方与消费方。

**Q30：本项目通过 MCP 接入了哪些工具？具体在面试流程的哪一步使用？**
> **A：** 接入了 **GitHub MCP Server**（分析开源项目结构、推荐学习仓库）与 **Web MCP Server**（抓取官方文档、技术博客）。主要在**复习规划阶段**使用：复习规划 Agent 根据薄弱点（如“不懂 Raft”）调用 MCP 检索 `etcd/raft` 源码或 Consul 官方文档链接，生成带真实 URL 的复习计划。

**Q31：MCP Server 和 MCP Client 在本项目中的对应关系？**
> **A：** 本项目的 AI 系统作为 **MCP Client**，GitHub/Web 服务作为 **MCP Server**。Client 通过 stdio 或 SSE 与 Server 建立连接，发送 `tools/call` 请求（如 `search_repos`），Server 执行后返回结构化 JSON 结果，供 LLM 理解并融入回答。

**Q32：如果 MCP 工具调用失败（如 GitHub API 限流），系统如何降级？**
> **A：** 设计**超时熔断与降级链路**：设置 5s 超时，失败重试 2 次后捕获异常。降级策略为：退回本地 RAG 检索预存的优质仓库白名单，并提示用户“当前网络受限，推荐本地精选资源”。同时记录失败日志，避免复习规划链路完全中断。

**Q33：为什么不直接用 Python requests 爬取网页，而要封装成 MCP？**
> **A：** 直接 requests 需为每个工具手写 Prompt 描述、参数解析、错误处理，与业务代码深度耦合。MCP 将工具抽象为标准接口，LLM 通过 Schema 自动理解工具能力，实现**即插即用**。此外，MCP 是下一代工具集成标准，符合项目“工程级应用”定位。

---

### 6. Skill 系统与动态难度

**Q34：Skill 系统与 Tool 调用的本质区别是什么？**
> **A：** **Tool 是无状态的单次函数调用**（如查天气、算公式），执行即结束；**Skill 是有状态的多轮交互模块**，内部维护独立的状态机，可跨多轮与用户交互。例如“知识讲解 Skill”需要确认用户是否理解、是否举例，才能退出并返回主流程。

**Q35：快速测验 Skill 的工作流程？**
> **A：** 触发后进入 Skill 子图：① 生成 3-5 道速答题（选择题/填空题）；② 逐题交互，实时判分；③ 汇总正确率与耗时；④ 生成总结报告（如“Redis 基础薄弱”）；⑤ 退出 Skill，将结果写回主 State，供评估 Agent 参考并调整后续题单。

**Q36：动态难度调节的状态机如何设计？三级难度如何划分？**
> **A：** 状态机状态：`EASY` / `NORMAL` / `HARD`。初始难度由 JD 职级决定（初级→EASY，高级→NORMAL）。状态转移规则：连续 2 题得分 >85 升一级，连续 2 题 <60 降一级。题库按难度标签预分类，状态切换时从对应池取题，确保难度平滑过渡。

**Q37：项目亮点提炼 Skill 如何帮助用户？**
> **A：** 通过多轮引导式提问（项目背景→技术难点→量化指标→个人贡献），挖掘用户经历中的闪光点。最终基于 STAR 法则生成结构化回答模板，直接用于简历优化或面试口述，解决“会做不会说”的痛点。

**Q38：Skill 如何做到“可插拔”？新增一个 Skill 需要哪些步骤？**
> **A：** 定义 `BaseSkill` 抽象类（含 `enter`、`run`、`exit` 方法）。新 Skill 继承基类，实现多轮交互逻辑；在 `SkillRegistry` 中注册名称与触发意图；编排层通过 `skill_name` 动态加载，无需修改主图结构。符合开闭原则。

---

### 7. 工程化与部署

**Q39：三种接入方式（CLI/WebSocket/REST）分别适用于什么场景？**
> **A：** **CLI**：开发者本地调试、快速测试 Agent 流转；**WebSocket**：前端网页实时音视频交互，支持服务器主动推送（如 AI 说话流、状态更新）；**REST**：第三方系统集成、批量导入 JD/简历、获取历史报告。

**Q40：WebSocket 如何与 LangGraph 的异步执行结合？**
> **A：** WebSocket 接收用户输入后，放入异步队列，调用 `graph.astream()` 流式执行。通过 `async for chunk in stream` 实时获取中间状态（如“思考中”“评估中”），经 WebSocket 推送给前端。LLM 流式输出通过 WebSocket 分片传输，降低首字延迟。

**Q41：音视频模块的技术选型？ASR 和 TTS 如何实现？**
> **A：** 前端通过 WebRTC/HTML5 `getUserMedia` 获取摄像头与麦克风。**ASR**：本地部署 Whisper Small/Base 将语音转为文本，或调用通义听悟 API；**TTS**：使用 Edge-TTS 或 ChatTTS 将 LLM 输出转为音频流，前端 `<audio>` 标签播放。本地优先选用轻量级模型，避免依赖外网。

**Q42：单用户本地部署为什么不用 Docker？如何管理依赖？**
> **A：** 单用户场景无需容器编排的复杂度。通过 `requirements.txt` 冻结依赖版本，使用 Python `venv` 或 `conda` 隔离环境。提供 `start.sh` 一键脚本：依次启动 Weaviate（embedded 模式）、Redis、MySQL 和 Python Web 服务，降低使用门槛。

**Q43：本地服务器启动后，如何在自己电脑上访问？涉及哪些网络配置？**
> **A：** 服务器配置应用监听 `0.0.0.0:PORT`，防火墙/安全组放行该端口（如 8000）。本地电脑通过浏览器访问 `http://服务器IP:PORT`。若在同一内网，直接 IP 访问；若需公网访问，使用服务器公网 IP 或 frp/ngrok 内网穿透。

**Q44：如何确保本地部署时各组件（Weaviate/Redis/MySQL）的可用性？**
> **A：** `start.sh` 中集成健康检查：Weaviate 检查 `curl localhost:8080/v1/.well-known/ready`，Redis 检查 `redis-cli ping`，MySQL 检查 `mysqladmin ping`。任一失败则等待重试 3 次。使用 `supervisord` 或 `systemd` 守护进程，崩溃后自动拉起。

**Q45：项目的日志和监控如何设计？**
> **A：** 使用 `loguru` 分级别记录：Agent 流转日志（INFO）、RAG 检索详情（DEBUG）、LLM 调用耗时与 Token 消耗（INFO）。关键链路（评估、RAG）埋点，输出结构化 JSON 日志。本地提供轻量看板（Streamlit/Gradio）实时查看会话状态与历史记录。

---

### 8. 项目拓展与优化

**Q46：如果面试人数从单用户扩展到 100 并发，架构需要哪些改动？**
> **A：** ① **状态持久化**：LangGraph checkpointer 从内存改为外部 Postgres，支持多实例共享状态；② **服务层**：WebSocket 层加负载均衡（Nginx），LLM 调用增加异步队列（Celery + Redis）；③ **数据层**：Weaviate 集群化，MySQL 读写分离；④ **限流**：单用户面试频率限制，防止资源耗尽。

**Q47：如何防止 LLM 面试官的“幻觉”（如编造不存在的八股文概念）？**
> **A：** 四层防护：① **RAG 约束**：面试官 Agent 的 Prompt 强制要求“基于检索到的参考题目与知识点提问，禁止编造”；② **Retriever 优先**：优先使用题库原题，减少生成；③ **评估检测**：评估 Agent 检测题目与标准答案的一致性；④ **Temperature 调低**至 0.1-0.3，减少随机性。

**Q48：项目中向量检索和 BM25 检索的优缺点分别是什么？为什么必须双路？**
> **A：** **向量检索**：优点是能捕捉同义词和语义关联（如“Redis 持久化”与“RDB/AOF”），缺点是可能丢失精确术语，对短文本关键词敏感度高。**BM25**：优点是关键词精准匹配、可解释性强，缺点是无法理解语义（如“CAP 理论”与“分布式一致性”）。双路互补，覆盖“语义相关”与“术语精确”两类需求。

**Q49：如何评估整个模拟面试系统的有效性？有哪些真实反馈指标？**
> **A：** 系统指标：`JD-题目匹配度`（人工抽检 >90%）、`评估一致性`（同一回答多次评分方差 <5%）。用户指标：`面试完成率`、`复习计划执行率`、用户主观 `NPS 评分`。长期追踪用户真实面试通过率与系统评分的相关性（Pearson 系数）。

**Q50：如果让你优化 RAG 检索速度，你会从哪些方面入手？**
> **A：** ① **向量量化**：Embedding 使用 INT8/Binary 量化，降低内存与计算量；② **索引调优**：Weaviate HNSW 参数调优（`efConstruction`、`ef`）；③ **预过滤**：先按 metadata（技术标签、难度）粗筛，再向量检索；④ **缓存**：高频 Query 的 Rerank 结果入 Redis 缓存；⑤ **并行化**：双路召回改为异步并行执行。

**Q51：在 LangGraph 中，如果某个 Agent 执行超时（如 Rerank 服务卡住），如何设计超时熔断？**
> **A：** Agent 节点包装 `asyncio.wait_for(coroutine, timeout=10)`，超时后捕获 `TimeoutError`，走降级路径（跳过 Rerank，直接返回 RRF Top5）。同时 State 中标记 `rerank_fallback=True`，后续评估 Agent 知晓此次检索未精排，适当放宽评分标准。

**Q52：复习规划 Agent 生成的计划如何保证可落地性？**
> **A：** ① **资源真实**：通过 MCP 获取真实存在的 GitHub 仓库与官方文档链接，避免死链；② **粒度细化**：计划拆解到“天”级别，明确每日学习目标（如“Day1：完成 Redis 哨兵模式配置实验”）；③ **关联薄弱点**：计划直接关联面试中的错题，而非泛泛而谈；④ **可验证**：设置检查点，要求用户完成代码或笔记。

**Q53：本项目中最难实现的技术点是什么？如何解决的？**
> **A：** 最难的是**多轮面试中的上下文感知追问**。难点在于追问需基于历史对话，但不能无限循环。解决方案：面试官 Agent 维护独立状态（`follow_up_count`、`last_topic`），结合短期记忆最近 3 轮对话；评估 Agent 输出结构化决策（`dig_deeper` / `move_on` / `give_hint`），通过 LangGraph 条件边精确控制流转。

**Q54：如何保证不同 Agent 使用的大模型 Prompt 不会相互干扰？**
> **A：** ① **物理隔离**：每个 Agent 独立 Prompt 文件（Jinja2 模板），按 `agents/{agent_name}/prompt.txt` 管理；② **Schema 约束**：每个 Agent 输出强制要求结构化格式（JSON/XML），经 Pydantic 校验；③ **单元测试**：为每个 Agent 编写单测，固定输入验证输出 Schema 与边界行为。

**Q55：项目中的数据安全与隐私如何保障（简历/JD 属于敏感信息）？**
> **A：** ① **本地优先**：核心卖点是本地部署，简历/JD 原始文件仅在内存处理，不经过第三方云服务；② **加密存储**：MySQL 中敏感字段（如手机号、公司名）AES 加密；③ **传输加密**：WebSocket  over TLS（WSS），HTTPS；④ **最小权限**：Weaviate/Redis 不暴露公网端口，仅本地回环访问；⑤ **定期清理**：原始 PDF 解析后删除，仅保留脱敏后的向量与文本。

