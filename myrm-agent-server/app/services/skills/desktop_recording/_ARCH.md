# services/skills/desktop_recording/

## 架构概述

Desktop Workflow 录制采集服务层。管理录制会话期间的后台原生 AX 树采集循环、生命周期启停、空闲自动停止及事件流持久注入。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 服务包入口，导出 DesktopCaptureTask | ✅ |
| `capture_task.py` | 核心 | 后台原生 AX 采集循环任务：轮询前台桌面树并追加录制事件至会话状态 | ✅ |
