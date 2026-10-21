# Wiki Knowledge Governance 模块架构说明（L3 · _ARCH.md）

## 1. 模块定位与职责（POS）
`app/services/wiki/governance/` 负责知识治理工作台（`KnowledgeGovernanceWorkbenchExpiryArchiveRevival`）的核心业务逻辑。
提供 90 天老化检测扫描、常青概念白名单豁免（`lifecycle: permanent`）、30 秒撤销缓冲区（Undo Buffer）以及物理隔离的归档与复活原子操作。

## 2. 架构设计原则与约束
1. **物理目录严格隔离**：归档目录为 `wiki_dir / "archive" / "concepts"`，与活跃目录平级，100% 避免 FTS5 全文索引穿透扫描。
2. **只读公共库安全保护**：外部挂载的 `public_dirs` 严格只读，治理扫描仅在当前 Agent 专属可写空间运行，绝不越权篡改只读库。
3. **白名单长效保护**：支持 Frontmatter `lifecycle: permanent` 或 `pinned: true` 声明，永久豁免 90 天老化判定。
4. **防手滑撤销缓冲区**：内存级 30 秒暂存，批量归档支持一键秒级 Undo。

## 3. 内部文件与接口清单

| 文件名 | 地位 | 核心职责 | 输入 (INPUT) | 输出 (OUTPUT) |
| :--- | :--- | :--- | :--- | :--- |
| `__init__.py` | Facade 门面 | 聚合导出治理 schemas 与服务 | 内部模块 | 统一向外暴露稳定 API |
| `schemas.py` | Core 实体 | 定义 ExpiringConceptInfo, GovernanceOverviewResult, GovernanceActionResult | 无 | 强类型数据契约 (DTO) |
| `freshness_service.py` | Core 引擎 | 90 天老化扫描、白名单过滤、延期、批量归档、撤销与复活 | schemas, structure, indexer | 治理业务操作结果 |
