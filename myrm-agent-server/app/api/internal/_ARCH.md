# api/internal/

## 架构概述

Control Plane → sandbox internal 控制端点（中断、killswitch）。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `agent_interrupt.py` | 模块 | CP-to-sandbox internal endpoint for interrupting agent execution | ✅ |
| `skills_killswitch.py` | 模块 | CP-to-sandbox internal endpoint for remote skill killswitch management | ✅ |
