# vault/

Wiki vault 域子包 — 路径 SSOT、生命周期、导出与 git 钩子。

## 架构概述

聚合 vault 全生命周期能力：路径解析与 legacy 迁移（`resolver`）、启动初始化与共享 archiver（`service`）、Obsidian-ready 导出（`export`）、git snapshot / status 钩子。模块名 `app.services.wiki.vault`。

上级文档：[../_ARCH.md](../_ARCH.md)

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 门面 | 聚合导出 resolver/service/export/git 全量公开符号 | ✅ |
| `resolver.py` | SSOT | 路径解析 + 友好库名标签映射（`resolve_shared_wiki_vault_labels`） + legacy 迁移 + `seed_agent_vault_from_default`（Second Brain preset 默认 vault→新 agent + SCHEMA.md seed） | ✅ |
| `service.py` | 生命周期 | 启动迁移、共享 archiver（cache key: llm + agent_id + manager + resolved_public_dirs + resolved_labels，支持跨源共享知识库动态挂载与名称映射注入） | ✅ |
| `export.py` | 核心 | Obsidian-ready full vault ZIP（harness archive + server graph preset） | ✅ |
| `git_snapshot.py` | 钩子 | `after_wiki_vault_mutation` SSOT + async git schedule (#23) | ✅ |
| `git_status.py` | 辅助 | `/wiki/stats` vault git visibility fields (Local/Tauri) | ✅ |

## 依赖

- `myrm_agent_harness.toolkits.wiki.core.structure` — `WikiStructure` (POS: vault paths)
- `app.services.wiki.obsidian.export` — `build_obsidian_vault_zip` (POS: Obsidian vault ZIP presets)
- `app.core.cron` — vault git snapshot 定时触发
