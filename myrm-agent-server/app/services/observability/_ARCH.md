# services/observability 模块架构

## 架构概述

任务运行时可观测性服务层。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `timeline/` | 子包 | 任务执行时序透视镜与技能调用追踪服务（步骤树、瀑布流、插嘴打断）。参见 [timeline/_ARCH.md](timeline/_ARCH.md) | ✅ |
