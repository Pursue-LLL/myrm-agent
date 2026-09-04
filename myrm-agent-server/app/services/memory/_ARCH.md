# services/memory 模块架构

## 架构概述

记忆服务层。按领域拆分为 11 个子目录：`backup/`（记忆数据备份与恢复、WebDAV/S3 远程备份策略与调度）、`archive/`（单用户 Memory Archive 导出与审查预检、安全合并恢复与回滚账本）、`behavioral/`（零模型成本确定性行为特征测量与 Profile 沉淀）、`command_center/`（个人大脑指挥中心聚合与洞察）、`diagnostics/`（独立 Memory Diagnostics 探针、质量治理、黄金召回基准与修复计划）、`evidence/`（证据回放、溯源审计与脱敏）、`extract_retry/`（记忆提取失败持久化重试队列与后台 worker、chat extraction LLM 解析）、`imports/`（导入 adapter 目录、导入审查会话、事务账本与崩溃安全回滚、Integration Memory 业务与同步守护、MCP Server 桥接）、`ledger/`（单用户记忆操作账本与 Guardian 调度/摘要聚合）、`operations/`（记忆 CRUD 业务处理器与 crud 子模块聚合、实体→DTO 呈现转换）、`shared_context/`（Shared Context 产品层治理、健康、历史证据与物化）。根目录仅保留 MemoryManager 依赖工厂门面。

## 子目录清单

| 目录 | 职责 |
|------|------|
| `behavioral/` | 零模型成本确定性行为特征测量服务（滑动窗口事件收集、双轨作息直方图与协作者聚合、Profile 记忆沉淀）。见 `behavioral/_ARCH.md` |
| `backup/` | 记忆数据备份与恢复服务；WebDAV/S3 远程备份 upload/download/list/delete 抽象、自动同步调度与远程恢复。见 `backup/_ARCH.md` |
| `archive/` | 单用户 Memory Archive 服务（聚合普通记忆/Shared Context/会话/回放/审计账本，内容脱敏与结构校验）；恢复服务（dry-run、hash 强校验、安全预检、journaled safe-merge、回滚账本、profile 并发保护）。见 `archive/_ARCH.md` |
| `command_center/` | 个人大脑指挥中心聚合服务（单用户/单沙箱可观测快照、trace run 聚合、`vector_persistence` 揭示）与洞察服务（影响证据、瀑布流、eval checks、迁移来源聚合等）。见 `command_center/_ARCH.md` |
| `diagnostics/` | Memory Diagnostics 服务与静态检查构建器、probe 结果归一化、质量治理、黄金召回基准、修复计划/执行器、SLO 汇总。见 `diagnostics/_ARCH.md` |
| `evidence/` | 证据回放与溯源服务（对话上下文切片检索、敏感凭据脱敏）。见 `evidence/_ARCH.md` |
| `extract_retry/` | 记忆提取持久化重试队列（幂等入队、退避重试、重启恢复、终态账本）与后台 worker；对指定 chat 重新调度 `auto_extract_memories`（含隐私保护上下文重建）；chat→agent extraction LLM 解析（`resolve_chat_extraction_llm.py`）。见 `extract_retry/_ARCH.md` |
| `imports/` | 导入 adapter 目录与解析器、dry-run dispatcher、导入审查会话编排、item-level 事务账本与崩溃安全回滚 journal、Integration Memory 业务服务与 Sync Daemon、MCP Server→IntegrationProvider 桥接（`mcp_bridge_provider.py`）。见 `imports/_ARCH.md` |
| `ledger/` | 单用户记忆操作账本（`record_event` 事件发布在持久化成功之后，杜绝 ghost event）、Guardian 调度策略（`guardian_policy.py`）与晨间摘要聚合。见 `ledger/_ARCH.md` |
| `operations/` | 记忆 CRUD 业务处理器（列表/创建/更新/回收站/归档导入/偏好），`crud_handlers.py` 作为门面聚合 `crud/` 子模块；实体→`MemoryItem` DTO 呈现（`presentation.py`）。见 `operations/_ARCH.md` |
| `shared_context/` | Shared Context 共享上下文服务（CRUD、绑定解析、写入提案生命周期与治理 policy）、记忆健康、历史证据、写入物化。见 `shared_context/_ARCH.md` |

## 根目录文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `manager_deps.py` | 门面 | MemoryManager FastAPI 依赖工厂（`get_memory_manager` / `get_crud_memory_manager` / `get_optional_memory_manager`），供 api 与 service handler 注入 | ✅ |
