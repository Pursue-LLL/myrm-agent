# core/artifacts/

## 架构概述

产物存储读写原语。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 包入口与导出 | — |
| `listener.py` | 模块 | Persists chat artifacts for deploy/hydrate; Artifact.id matches SSE file_id | ✅ |
| `processor.py` | 模块 | 业务层工件处理器 | ✅ |
