# services/memory/backup 模块架构

## 架构概述

记忆数据备份/恢复服务与远程备份策略。WebDAV/S3 云端备份的 upload/download/list/delete 抽象和实现、自动同步调度（创建→上传→轮转）和远程恢复流程。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `backup.py` | 核心 | 记忆数据备份与恢复服务 | — |
| `backup_remote.py` | 核心 | 远程备份策略模块。WebDAV/S3 云端备份的 upload/download/list/delete 抽象和实现 | ✅ |
| `backup_remote_scheduler.py` | 核心 | 远程备份自动同步调度。执行单次远程备份周期(创建→上传→轮转)和远程恢复流程 | ✅ |
| `backup_remote_utils.py` | 辅助 | 远程备份工具函数。桥接 VolumeBackupStrategy 与远程存储，提供可导出备份创建和恢复 | ✅ |
