---
name: cross-harness-skill-discovery
description: "Automatically discover, normalize dialect frontmatter, resolve namespace collisions, and hot-mount skills authored across different local agent environments (Cursor, Claude, OpenClaw, Windsurf)."
version: "1.0.0"
category: "engineering"
tags:
  - cross-harness
  - skill-discovery
  - multi-agent
  - dialect-normalizer
  - hot-mount
allowed-tools:
  - file_write_tool
  - file_read_tool
---

# Cross-Harness Standard Skill Auto-Discovery & Hot-Mount (跨环境标准技能自动发现与热挂载技能)

## Overview

A dedicated interoperability skill for developers working across diverse AI Agent ecosystems (e.g. Cursor, Claude Desktop, OpenClaw, Windsurf, Hermes, Doubao).

Instead of forcing developers to manually rewrite or copy `SKILL.md` bundles between different toolchains, this skill establishes an automatic **Multi-Harness Discovery & Normalization Protocol**.

---

## 4-Stage Discovery & Normalization Pipeline (四阶自动发现与归一化流水线)

```
[Stage 1: Multi-Root Filesystem Probing (多源标准根目录探测)]
  - Probe standard user directory paths:
    ├── `~/.cursor/skills/` & `~/.cursor2/.cursor/skills/`
    ├── `~/.claude/skills/`
    ├── `~/.openclaw/skills/`
    └── `~/.windsurf/skills/`
         ↓
[Stage 2: Dialect Normalization (方言转译与契约归一化)]
  - Map ecosystem-specific frontmatter variations to Myrm Agent Skills SSOT:
    ├── `tools:` -> `allowed-tools:`
    ├── `requirements:` -> `requires:`
    └── `system_prompt_overlay:` -> Markdown instructions body
         ↓
[Stage 3: Namespace Collision & Source Isolation (命名空间防冲突与源隔离)]
  - Prefix discovered skills with vendor scopes (e.g. `cursor:automate`, `claude:canvas`)
  - Enforce Read-Only mounting from external source folders (preventing accidental tampering)
         ↓
[Stage 4: In-Memory Hot Registration (零重启内存热注册)]
  - Register sanitized descriptors into Myrm's active skill registry
  - Expose discovered skills to prompt suggestions and capability chips immediately
```

---

## Discovered Skill Manifest Contract (`docs/audits/cross-harness-inventory.md`)

```markdown
# 跨 Harness 本地技能发现与挂载清单

- **扫描时间**: YYYY-MM-DD HH:mm:ss
- **检测到外部生态**: Cursor (12 个), Claude Desktop (4 个), OpenClaw (8 个)
- **挂载模式**: 隔离命名空间 · 纯只读挂载 (Read-Only)

---

## 一、已挂载跨环境技能资产列表 (Discovered Skills)

| 命名空间技能 ID | 原生宿主环境 | 物理源路径 | 状态 |
|---|---|---|---|
| `cursor:automate` | Cursor | `~/.cursor2/.cursor/skills-cursor/automate/SKILL.md` | ✅ 挂载成功 |
| `cursor:canvas` | Cursor | `~/.cursor2/.cursor/skills-cursor/canvas/SKILL.md` | ✅ 挂载成功 |
| `claude:durable-objects`| Claude | `~/.claude/skills/durable-objects/SKILL.md` | ✅ 挂载成功 |
| `openclaw:healthcheck` | OpenClaw | `~/.openclaw/skills/healthcheck/SKILL.md` | ✅ 挂载成功 |

---

## 二、方言转译兼容性处理 (Dialect Normalization)
- **Cursor 兼容**: 自动映射 `allowed-tools` 与 `subagent_type` 元数据。
- **Claude 兼容**: 提取 `model_instructions` 并转换为标准 Markdown SOP 章节。
- **OpenClaw 兼容**: 兼容旧版 `tools_required` 字段并降级为环境 preflight 校验。
```

---

## Hard Invariants
- **Strict Read-Only Enforcement**: External skills are mounted as immutable references. Never write, delete, or modify files located outside the current project workspace.
- **Fail-Safe Dialect Fallback**: If an external `SKILL.md` has invalid YAML or missing mandatory fields, gracefully skip it with a warning rather than aborting the discovery scan.
