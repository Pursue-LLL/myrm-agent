# core/artifacts/

## 架构概述

产物存储读写原语。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 包入口与导出 | — |
| `listener.py` | 模块 | Deploy DB upsert + sandbox path resolve；`Artifact.id` 等于 SSE 的 `file_id`；同一个 `file_id` 再次 upsert 只追加版本（并发时输掉插入的一方并入已有行）；upsert 带 `source_path` 时写入或更新该列，不带则保持原值；预检阶段补建 artifact 时把文件写进来源会话的 vault | ✅ |
| `processor.py` | 模块 | 业务层工件处理器（LocalArtifactProcessor）；reference-only persist，文件身份按（会话, 真实路径）稳定；resolved_path SSOT；upsert 时把文件路径换算成 `source_path` 一并登记；upsert 成功才 emit | ✅ |
| `source_path.py` | 模块 | `Artifact.source_path` 的编码：工作区内存相对 POSIX 路径、工作区外存绝对路径（`to_source_path`），同一个文件的任何写法得到同一个值；`from_source_path` 还原成路径（同一个拼接表达式读两种形态） | ✅ |

## 测试

- `tests/core/artifacts/test_processor_oversized_shareable.py` — Local 超大可分享 reference-only persist、非 shareable skip、processor→deliverable 集成（含 sandboxes/{chat_id}/ 路径矩阵）
- `tests/core/artifacts/test_processor_short_file_id.py` — short_file_id 透传
