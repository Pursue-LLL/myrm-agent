# core/artifacts/

## 架构概述

产物存储读写原语。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 包入口与导出 | — |
| `listener.py` | 模块 | Deploy DB upsert + sandbox path resolve；`Artifact.id` 等于 SSE 的 `file_id`；同一个 `file_id` 再次 upsert 只追加版本（并发时输掉插入的一方并入已有行）；预检阶段补建 artifact 时把文件写进来源会话的 vault | ✅ |
| `processor.py` | 模块 | 业务层工件处理器（LocalArtifactProcessor）；reference-only persist，文件身份按（会话, 真实路径）稳定；resolved_path SSOT；upsert 成功才 emit | ✅ |

## 测试

- `tests/core/artifacts/test_processor_oversized_shareable.py` — Local 超大可分享 reference-only persist、非 shareable skip、processor→deliverable 集成（含 sandboxes/{chat_id}/ 路径矩阵）
- `tests/core/artifacts/test_processor_short_file_id.py` — short_file_id 透传
