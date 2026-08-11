# obsidian/

Obsidian 集成域子包 — 导入适配与导出 presets。

## 架构概述

聚合 Obsidian 双向能力：导入（`adapter`，frontmatter/inline tags/images 转换，生产经 router → harness `publish_raw`）与导出（`export`，`.obsidian/graph.json` + README + full vault ZIP presets）。模块名 `app.services.wiki.obsidian`。

上级文档：[../_ARCH.md](../_ARCH.md)

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 门面 | 聚合导出 adapter/export 公开符号 | ✅ |
| `adapter.py` | 适配器 | Obsidian Vault 导入：`prepare_obsidian_file()` 转换 frontmatter/inline tags/images；`adapt_obsidian_file()` 仅测试/legacy 直写；生产 import 经 `router` → harness `publish_raw` | ✅ |
| `export.py` | 适配器 | `.obsidian/graph.json` + README for Settings download | ✅ |

## 依赖

- `myrm_agent_harness.utils.markdown_frontmatter` — `parse_frontmatter` (POS: frontmatter SSOT)
- `myrm_agent_harness.toolkits.wiki.core.frontmatter_contract` — `infer_type_for_import` / `serialize_frontmatter` (POS: wiki page type gate SSOT)
- `app.services.wiki.vault` — vault 路径与 export 目标
