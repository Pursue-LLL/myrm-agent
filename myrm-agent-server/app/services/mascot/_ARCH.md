# services/mascot/

## 架构概述

桌宠 **Mascot** 业务服务：把流式事件映射为桌宠动画状态（`MascotStatus`）。`agent/streaming.py` 把结果写入事件的 `mascot_status` 字段，前端 `messageStream/handleMessageStream.ts` 据此切换桌宠动画。与 `companion/` 分工见 [../_ARCH.md](../_ARCH.md) 术语表。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `status_mapper.py` | 核心 | MascotStateMapper、MascotStatus 枚举 | — |
| `__init__.py` | 入口 | 公开导出 | — |
