# vault/

Wiki vault 域子包 — 路径 SSOT、生命周期、导出与 git 钩子。

## 架构概述

聚合 vault 全生命周期能力：路径解析与 legacy 迁移（`resolver`）、启动初始化与共享 archiver（`service`）、Obsidian-ready 导出（`export`）、git snapshot / status 钩子。模块名 `app.services.wiki.vault`。

上级文档：[../_ARCH.md](../_ARCH.md)

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 门面 | 聚合导出 resolver/service/export/git 全量公开符号 | ✅ |
| `resolver.py` | SSOT | 路径解析 + 友好库名标签映射（`resolve_shared_wiki_vault_labels`） + legacy 迁移 + `seed_agent_vault_from_default` + `is_vault_ready` / `vault_has_wiki_content` 挂载库感知与 `must_exist` 物理防护 | ✅ |
| `service.py` | 生命周期 | 启动迁移、共享 archiver（cache key: llm + agent_id + manager + resolved_public_dirs + resolved_labels，支持跨源共享知识库动态挂载与名称映射注入；无模型调用直接 `TypeError`，因为不带模型的 archiver 会占住 vault 唯一的编译 worker 槽位并让它取走的每个编译都失败）· `get_wiki_structure`：仅读写文件的场景（去重扫描、卫生清单、`.wikiignore`、原文落盘）拿 vault 布局，不构造 archiver、不启动 worker | ✅ |
| `export.py` | 核心 | Obsidian-ready full vault ZIP（harness archive + server graph preset） | ✅ |
| `git_snapshot.py` | 钩子 | `after_wiki_vault_mutation` SSOT + async git schedule (#23) | ✅ |
| `git_status.py` | 辅助 | `/wiki/stats` vault git visibility fields (Local/Tauri) | ✅ |

## 依赖

- `myrm_agent_harness.toolkits.wiki.core.structure` — `WikiStructure` (POS: vault paths)
- `app.services.wiki.obsidian.export` — `build_obsidian_vault_zip` (POS: Obsidian vault ZIP presets)
- `app.core.cron` — vault git snapshot 定时触发
