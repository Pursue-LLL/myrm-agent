# services/system/

## 架构概述

系统运维、存储维护与技术支持服务模块。负责聚合系统环境元数据、Doctor 健康检查快照、脱敏 Agent Profile 配置与排障日志，提供一键脱敏支持排障包（Support Debug Bundle）及 SQLite 会话存储优化（FTS 紧凑化、VACUUM 空闲页回收与 WAL 截断）。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 包入口 | 模块导出与初始化 | ✅ |
| `storage_service.py` | 核心 | 优化前的磁盘余量预检、SQLite 数据三元组拆解、安全热备份（复用 harness `hot_copy_database`）及异步全量优化执行 | ✅ |
| `storage_layout.py` | 核心 | 存储占用台账的数据布局声明：按 settings 把各类别（对话库、检查点库、工作区、检索索引、长期记忆、活动日志、数据库备份、状态快照）映射到路径，记忆与日志可被部署迁到状态目录之外（按实际所在位置计量），备份目录取自 `database/operations/backup.backup_dir_for`；状态目录里没被任何类别认领的部分由 harness 归入「其他」。归属规则（最深声明路径优先、数据库日志文件随主库、符号链接不跟随）属 harness，这里只声明路径 | ✅ |
| `checkpoint_history_service.py` | 核心 | 检查点历史回收的定时入口：对进程级 checkpointer 执行一次 keep-latest 剪枝（LangGraph 每步写一份全量检查点、恢复只读各会话最新一份，历史只增不减）；checkpointer 不支持剪枝（内存模式）时静默跳过，失败只记 WARNING、下个周期续做，从不向调度器抛错 | ✅ |
| `support_bundle_service.py` | 核心 | 结构化系统诊断信息聚合与内存 ZIP 归档生成（带双重脱敏、超时保护与体积熔断） | ✅ |
| `vault_purge_service.py` | 核心 | 安全金库清空编排器（入口先拒绝：网关仍有运行中会话时抛 `VaultPurgeBusyError`，API 层映射 409；仅覆盖网关已登记的执行、清空期间新开的会话不受阻；清空锁只让多次清空互斥、不阻止其它写入方；FTS5 逆序清空、按聊天停止运行时工作并清除会话 checkpoint 线程与会话授权（先于聊天行删除，被中断的清空不会留下再也列不出的状态）、同一事务内按 `chat_bound_rows.CHAT_BOUND_TABLES` 清除只存聊天 id 的 widget 数据 / 审批 / 主动承诺 / fission 记录并清空记忆管线表、自增序列/游标重置、聊天行删除后批量清理沙箱 worktree 与工作空间（均委托 `services/chat/chat_disposal`；仍有未保存改动的 worktree 保留并计入 `kept_sandboxes`）、白名单资产持久化与物理磁盘空间紧凑化） | ✅ |
| `model_ping_service.py` | 核心 | 模型连通性与 TTFT/吞吐量即时探测服务（轻量自检探针与健康状态判断） | ✅ |

> 整实例导出/导入与恢复点（更新前快照）已迁至 [`../instance_archive/`](../instance_archive/_ARCH.md)。
