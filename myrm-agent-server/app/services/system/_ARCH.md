# services/system/

## 架构概述

系统运维、存储维护与技术支持服务模块。负责聚合系统环境元数据、Doctor 健康检查快照、脱敏 Agent Profile 配置与排障日志，提供一键脱敏支持排障包（Support Debug Bundle）、全量数据 Takeout 导出及 SQLite 会话存储优化（FTS 紧凑化、VACUUM 空闲页回收与 WAL 截断）。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 包入口 | 模块导出与初始化 | ✅ |
| `storage_service.py` | 核心 | 存储目录容量探针、SQLite 数据三元组拆解、安全热备份及异步全量优化执行 | ✅ |
| `support_bundle_service.py` | 核心 | 结构化系统诊断信息聚合与内存 ZIP 归档生成（带双重脱敏、超时保护与体积熔断） | ✅ |
| `takeout_service.py` | 核心 | 用户个人全量数据资产（SQLite 数据库事务快照、Markdown Wiki、自定义技能、工件产物）标准化便携 Takeout 打包服务 | ✅ |
