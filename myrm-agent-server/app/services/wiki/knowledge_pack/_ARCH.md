# Knowledge Pack 模块架构说明（L3 · _ARCH.md）

## 1. 模块定位与职责（POS）
`app/services/wiki/knowledge_pack/` 是智能体每轮知识包前置主动注入（`KnowledgePackProactiveInjectionPerAgentTurn`）的核心领域模块。
负责在每轮 Agent 交互前，按会话或 Agent 绑定的外挂知识库进行非阻塞、高置信度段落提取、Jaccard 跨库语义去重、严格 Token/字符预算硬截断与 150ms 熔断保护。

## 2. 架构设计原则与约束
1. **0 冗余数据库实体**：复用既有的 `shared_contexts` 表与 `Agent.memory_policy` 配置字段，不增加无用表。
2. **Prompt Cache 绝对零污染**：动态检索结果仅注入 HumanMessage 前置信封，System Prompt 保持 100% 静态不变。
3. **预算截断与硬限制**：最多 3 个关键段落，单段 ≤ 200 字符，总字符 ≤ 600 字符。
4. **150ms 严格超时降级**：后台预热超时自动静默跳过，绝不阻塞用户首字输出（TTFT 零负面影响）。
5. **Jaccard 相似度去重**：相似度 ≥ 0.70 的重复段落直接剔除，确保信息高增益。

## 3. 模块内部文件清单与接口职责

| 文件名 | 地位 | 核心职责 | 输入 (INPUT) | 输出 (OUTPUT) |
| :--- | :--- | :--- | :--- | :--- |
| `__init__.py` | Facade 门面 | 聚合导出模块内所有核心契约与算法 | 内部各子模块 | 统一向外暴露稳定 API |
| `schemas.py` | Core 实体 | 定义 KnowledgePackConfig, RelevantSnippet, ProactiveKnowledgeResult | 无 | 强类型数据传输对象 (DTO) |
| `selector.py` | Pipeline 引擎 | 段落检索、Jaccard 语义去重、硬预算截断与异步 Vault 扫描 | schemas, resolver | ProactiveKnowledgeResult |
