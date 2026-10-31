# Knowledge Pack 模块架构说明（L3 · _ARCH.md）

## 1. 模块定位与职责（POS）
`app/services/wiki/knowledge_pack/` 是智能体每轮知识包前置主动注入（`KnowledgePackProactiveInjectionPerAgentTurn`）的核心领域模块。
负责在每轮 Agent 交互前，按会话或 Agent 绑定的外挂知识库进行非阻塞、高置信度段落提取、Jaccard 跨库语义去重、严格 Token/字符预算硬截断与 150ms 熔断保护。

## 2. 架构设计原则与约束
1. **0 冗余数据库实体**：复用既有的 `shared_contexts` 表与 `Agent.memory_policy` 配置字段，不增加无用表。
2. **Prompt Cache 布局隔离**：动态检索结果仅注入 HumanMessage 前置信封，System Prompt 保持静态不变。
3. **预算截断与硬限制**：最多 3 个关键段落，单段 ≤ 200 字符，总字符 ≤ 600 字符。
4. **150ms 超时降级**：超过 150ms 的检索返回空结果、不注入，对话照常进行。扫描函数内部没有 `await`，扫描一旦开始就不会让出事件循环，所以超时只在扫描结束后生效，不能打断一次耗时更长的扫描；耗时由查询词数上限（原则 7）与索引规模约束。
5. **Jaccard 相似度去重**：相似度 ≥ 0.70 的重复段落直接剔除，确保信息高增益。
6. **发布门禁（两层）**：层 1 经 harness 的 `search_published_index` 只读打开 vault 的 FTS 索引，draft、blocked 与 sidecar 行在匹配查询内就被排除，排名与 `LIMIT` 只数已发布页面，草稿再多也挤不掉已发布页面；没有发布元数据表的旧索引整体按已发布读取。层 2 在读页面文件时：读到的每份页面文本再过 harness 的 `resolve_publish_status`（索引可能落后于文件），draft 与 blocked 页整页跳过（索引命中的页面也一样，页面文件才是发布状态的依据），读不出的页面同样整页跳过；只有没有页面文件的索引行（如 raw 来源）才用索引里存的文本。缺失或未知的状态按已发布处理，与 wiki 全局约定一致。片段取自去掉 frontmatter 的正文。
7. **查询词确定性**：层 1 的 `OR` 查询取问题里最靠前的 8 个词（字母数字词与相邻汉字二元组，按出现位置排列、各取一次，不足 2 个字符的不取），同一个问题在任何进程里都得到同一条查询；词的取舍不依赖集合的迭代顺序。层 2 用同一批词（去重后的集合）逐段计数打分。

## 3. 模块内部文件清单与接口职责

| 文件名 | 地位 | 核心职责 | 输入 (INPUT) | 输出 (OUTPUT) |
| :--- | :--- | :--- | :--- | :--- |
| `__init__.py` | Facade 门面 | 聚合导出模块内所有核心契约与算法 | 内部各子模块 | 统一向外暴露稳定 API |
| `schemas.py` | Core 实体 | 定义 KnowledgePackConfig, RelevantSnippet, ProactiveKnowledgeResult | 无 | 强类型数据传输对象 (DTO) |
| `selector.py` | Pipeline 引擎 | 层 1 按问题里出现顺序取前 8 个词建 OR 查询、只读 FTS 索引取已发布页面，层 2 扫 markdown；页面文件再过发布门禁并剥离 frontmatter 后的段落检索、Jaccard 语义去重、硬预算截断与异步 Vault 扫描 | schemas, resolver, harness 的 `search_published_index`、`tokenize_for_fts`、`resolve_publish_status` 与 `parse_frontmatter` | ProactiveKnowledgeResult |
