# Knowledge Pack 模块架构说明（L3 · _ARCH.md）

## 1. 模块定位与职责（POS）
`app/services/wiki/knowledge_pack/` 是智能体每轮知识包前置主动注入（`KnowledgePackProactiveInjectionPerAgentTurn`）的核心领域模块。
负责在每轮 Agent 交互前，按会话或 Agent 绑定的外挂知识库进行非阻塞、高置信度段落提取、Jaccard 跨库语义去重、严格 Token/字符预算硬截断与 150ms 熔断保护。

## 2. 架构设计原则与约束
1. **0 冗余数据库实体**：复用既有的 `shared_contexts` 表与 `Agent.memory_policy` 配置字段，不增加无用表。
2. **Prompt Cache 布局隔离**：动态检索结果仅注入 HumanMessage 前置信封，System Prompt 保持静态不变。
3. **预算截断与硬限制**：最多 3 个关键段落，单段 ≤ 200 字符，总字符 ≤ 600 字符。
4. **150ms 超时降级**：超过 150ms 的检索返回空结果、不注入，对话照常进行。扫描函数内部没有 `await`，扫描一旦开始就不会让出事件循环，所以超时只在扫描结束后生效，不能打断一次耗时更长的扫描；耗时由问题长度与查询词数上限（原则 7）、索引规模和只在无索引库上运行的第 2 层（原则 9）约束。
5. **Jaccard 相似度去重**：相似度 ≥ 0.70 的重复段落直接剔除，确保信息高增益。
6. **发布门禁（两层）**：层 1 经 harness 的 `search_published_index` 只读打开 vault 的 FTS 索引，draft、blocked 与 sidecar 行在匹配查询内就被排除，排名与 `LIMIT` 只数已发布页面，草稿再多也挤不掉已发布页面；没有发布元数据表的旧索引整体按已发布读取。层 2 在读页面文件时：读到的每份页面文本再过 harness 的 `resolve_publish_status`（索引可能落后于文件），draft 与 blocked 页整页跳过（索引命中的页面也一样，页面文件才是发布状态的依据），读不出的页面同样整页跳过；只有没有页面文件的索引行（如 raw 来源）才用索引里存的文本。缺失或未知的状态按已发布处理，与 wiki 全局约定一致。片段取自去掉 frontmatter 的正文。
7. **查询词确定性**：问题只读前 1000 个字符。去掉 harness 的停用词（`STOP_WORDS`）后取最靠前的 16 个词：字母数字词与相邻汉字二元组，按出现位置排列、各取一次；不足 2 个字符的词只在没有更长的词时才用。停用词在取上限之前就去掉，客套话（「请问能不能帮我……」）不会挤掉主题词。同一个问题在任何进程里都得到同一条 `OR` 查询，词的取舍不依赖集合的迭代顺序；两层读同一份词表。
8. **相关度门槛与置信度**：索引对任何问题都返回排名最高的页面，不管问题有没有答案。两层都只在「标题加最佳段落」里命中至少 2 个不同的查询词（问题只有 1 个词时要 1 个），且有 3 个词、或有 1 个词在标题里时，才留下这段，不达标的页面不注入，所以库里没有答案的问题不注入任何片段。置信度就是命中词数占查询词数的比例，两层同一个定义，跨库排序不再取决于库的绑定顺序。字母数字词按整词计（`me` 不在 `memory` 里），4 个字符以上的词可以是更长词的开头（`agent` 在 `agents` 里）；汉字词按子串计。这是词面规则，不是语义判断。
9. **层 2 只服务没有可读索引的库**：有可读索引的库由索引作答，空答案也算——为读 15 个页面而列出上万个文件，代价高于它能找到的。没有索引或索引读不出来时，层 2 按文件名取前 15 个 markdown 文件（`heapq.nsmallest`，不排序整个目录列表），读哪些页面不取决于文件系统的列举顺序；索引之外的页面不会被这一层扫到。

## 3. 模块内部文件清单与接口职责

| 文件名 | 地位 | 核心职责 | 输入 (INPUT) | 输出 (OUTPUT) |
| :--- | :--- | :--- | :--- | :--- |
| `__init__.py` | Facade 门面 | 聚合导出模块内所有核心契约与算法 | 内部各子模块 | 统一向外暴露稳定 API |
| `schemas.py` | Core 实体 | 定义 KnowledgePackConfig, RelevantSnippet, ProactiveKnowledgeResult | 无 | 强类型数据传输对象 (DTO) |
| `query_terms.py` | 辅助 | 问题的查询词与相关度：`search_terms` 去停用词后按出现顺序取前 16 个词，`carried_terms` 数一段文本带有几个词，`paragraph_relevance` 给「标题加段落」打相关度并设门槛，`tokenize_text` 供去重 | harness 的 `STOP_WORDS` | `MAX_QUERY_CHARS`、`ordered_terms`、`tokenize_text`、`search_terms`、`carried_terms`、`paragraph_relevance` |
| `selector.py` | Pipeline 引擎 | 层 1 用查询词建 OR 查询、只读 FTS 索引取已发布页面，层 2 只扫没有可读索引的库的 markdown；两层都按 `paragraph_relevance` 设门槛并把它作置信度；页面文件再过发布门禁并剥离 frontmatter 后的段落检索、Jaccard 语义去重、硬预算截断与异步 Vault 扫描 | schemas, query_terms, harness 的 `search_published_index`、`resolve_publish_status` 与 `parse_frontmatter` | ProactiveKnowledgeResult |
