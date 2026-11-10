# app/schemas/memory 模块架构

记忆域共享 Pydantic DTO。api 与 services 层共用，不含 HTTP 路由逻辑。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `crud.py` | 核心 | Memory CRUD、偏好、评分、导出请求/响应模型 | ✅ |
| `archive.py` | 核心 | 归档、导入、回滚请求/响应模型；`MemoryImportReadiness`/`MemoryImportReadinessIssue`（含可选 `settings_path` 深链） | ✅ |
| `import_sources.py` | 核心 | 记忆导入来源词汇表 SSOT（`ImportSource`/`ImportRequestSource`/`IMPORT_SOURCE_IDS`/`import_source_label`）；API 请求白名单、适配器分发、迁移来源清单与命令中心投影全部由此派生 | ✅ |
| `import_warning_codes.py` | 核心 | 记忆导入告警码词汇表 SSOT（`ImportWarningCode`/`IMPORT_WARNING_CODES`）；适配器发射集由契约测试比对（发射 ⊆ 词表、词表 ⊆ 发射），六语言文案覆盖由前端契约测试比对 | ✅ |
| `command_center/` | 子包 | 记忆指挥中心 HTTP 契约，按响应族分 9 个模块（overview / economics / replay / diagnostics / migration / graph / actions / recall / evidence），`__init__` 聚合 52 个模型；`MemoryCommandRuntimeStatus` 含 `vector_persistence`（persistent/memory_fallback/unavailable）。见 [command_center/_ARCH.md](command_center/_ARCH.md) | ✅ |
| `radar.py` | 核心 | 动态偏好雷达状态响应、手动微调请求（拒绝未知字段，写错字段名报错而非静默忽略）与隐式反馈记录 DTO 模型 | ✅ |
| `tool_guidance.py` | 核心 | 工具规约与动态黄金指南 DTO 模型（条目、聚合组、列表与置顶请求） | ✅ |
| `domain_mesh.py` | 核心 | 三域认知网格与渐进式分层数据契约：L0/L1/L2 高亮、域桶概览与下钻响应 | ✅ |

