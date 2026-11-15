# tasks/executors/

## 架构概述

后台任务执行器实现。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Task executors. | ✅ |
| `image_executor.py` | 模块 | Image task executor; resolves config per task via `image_config_resolver` and returns the stored image's `media://` reference; `image_task_result` is the one result shape (also used by the E2E fixture). | ✅ |
| `video_executor.py` | 模块 | Video task executor implementation. | ✅ |
