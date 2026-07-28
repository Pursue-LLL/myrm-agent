# api/wiki/

## 架构概述

Wiki 知识库 HTTP 层：Brain Console REST 入口。Vault 路径 SSOT 见 `app/services/wiki/vault_resolver.py`（`{harness_dir}/wiki`）。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Wiki API router. | ✅ |
| `router.py` | 路由 | REST：…；pending approve 422 `invalid_frontmatter` / **`stale_pending`**；**tree/move** 经 `reindex_concepts_after_move`；**repair-publication** 仅 grandfather 缺失 publish_status（跳过 intentional draft/blocked，响应含 `files_skipped_intentional_drafts`）；… | ✅ |
