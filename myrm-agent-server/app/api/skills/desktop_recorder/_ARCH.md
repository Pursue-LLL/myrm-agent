# api/skills/desktop_recorder/

## 架构概述

Desktop Workflow Skill Recorder HTTP 接口层。提供桌面操作录制会话管理、前台 AX 事件收集、意图规划分析、SKILL.md 编译与本地技能发布等端点。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `router.py` | 路由 | Desktop Workflow Skill Recorder API 路由与会话生命周期管理 | ✅ |
| `schemas.py` | 契约 | 桌面工作流录制请求/响应 Pydantic 模型与录制会话状态容器 | ✅ |
