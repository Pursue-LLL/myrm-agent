# services/memory/archive 模块架构

## 架构概述

单用户 Memory Archive 导出与审查预检、单用户 Memory Archive 安全合并恢复与回滚账本。提供归档分区 dry-run、payload/plan hash 强校验、恢复前安全预检、journaled safe-merge 恢复、关系型恢复账本、恢复后诊断 metadata 挂载、中断恢复回滚、profile 并发保护、Shared Context/会话/回放/审计恢复和精准回滚，不包含多租户或控制平面语义。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `archive.py` | 核心 | 单用户 Memory Archive 服务。基于 Harness archive DTO 聚合普通记忆、Shared Context、会话、回放事件和记忆审计账本，执行内容脱敏并提供导入前结构校验，不包含多租户或控制平面语义 | ✅ |
| `archive_restore.py` | 核心 | 单用户 Memory Archive 恢复服务。提供归档分区 dry-run、payload/plan hash 强校验、恢复前安全预检、journaled safe-merge 恢复、关系型恢复账本、恢复后诊断 metadata 挂载、中断恢复回滚、profile 并发保护、Shared Context/会话/回放/审计恢复和精准回滚，不包含多租户或控制平面语义 | ✅ |
| `archive_restore_common.py` | 辅助 | 归档恢复共享原语。集中恢复状态常量、校验辅助、mutation-ref 构建和 JSON 强制转换，无业务副作用 | — |
| `archive_restore_executor.py` | 核心 | 归档恢复执行层。写入 memory/Shared Context/conversation/replay/audit 分区并记录可回滚账本 | ✅ |
| `archive_restore_planner.py` | 辅助 | 归档恢复预检层。生成 section 级 safe-merge dry-run plan，只读当前库和归档 manifest/data，不写入业务状态 | — |
| `archive_restore_rollback.py` | 辅助 | 归档恢复回滚执行层。按恢复账本精准撤销 memory、Shared Context、conversation、replay 和 audit 写入 | ✅ |
