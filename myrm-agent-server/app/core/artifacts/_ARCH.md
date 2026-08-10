# core/artifacts/

## 架构概述

产物存储读写原语。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 包入口与导出 | — |
| `listener.py` | 模块 | Persists chat artifacts for deploy/hydrate; Artifact.id matches SSE file_id | ✅ |
| `processor.py` | 模块 | 业务层工件处理器；Local 模式对超大可分享工件（HTML/PDF 等）走 reference-only persist（stat 不读内容），供 IM deliverable 深链 | ✅ |

## 测试

- `tests/core/artifacts/test_processor_oversized_shareable.py` — Local 超大可分享 reference-only persist、非 shareable skip、processor→deliverable 集成
- `tests/core/artifacts/test_processor_short_file_id.py` — short_file_id 透传
