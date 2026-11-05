# api/wiki/

## 架构概述

Wiki 知识库 HTTP 层：Brain Console REST 入口。Vault 路径 SSOT 见 `app/services/wiki/vault`（`{harness_dir}/wiki`）。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Wiki API router. | ✅ |
| `router.py` | 路由 | 组合根：按原路径顺序挂载 `routes/` 下的全部领域路由，并注册 ingest stream；端点细节见各子模块与 [`routes/_ARCH.md`](routes/_ARCH.md) | ✅ |
| `routes/` | 子包 | 全部 wiki 业务路由（query/dedup/stats/tree/mutations/queue/insights/imports/url_import/video_import/meeting/vault/portability/sources/governance/layers/maintain/obsidian_binding/ingest_stream + 支撑模块），逐项见 [routes/_ARCH.md](routes/_ARCH.md) | ✅ |
| `archiver_dependency.py` | 依赖 | `get_scoped_wiki_archiver`：所有 wiki 路由共用的请求级 archiver 依赖，绑定用户配置的模型与所请求的 vault（编译、问答、变更类端点用它）；只读写 vault 文件的端点改用 `app.services.wiki.vault.get_wiki_structure`，不会在没有模型时构造出占住编译 worker 槽位的 archiver | ✅ |
