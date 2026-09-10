---
name: plugin-syntax-migrator-doctor
description: "Scan, diagnose, and idempotently auto-fix deprecated plugin frontmatter, obsolete tool references, and legacy schema declarations across local agent workspaces."
version: "1.0.0"
category: "engineering"
tags:
  - doctor
  - auto-fix
  - syntax-migration
  - deprecated-plugins
  - schema-repair
allowed-tools:
  - file_write_tool
  - file_read_tool
---

# Deprecated Plugin Syntax Migration & Doctor Auto-Fix (废弃插件语法迁移与体检自愈技能)

## Overview

A dedicated maintenance and diagnostics skill inspired by `openclaw doctor --fix`.

As agent standards, tool namespaces, and frontmatter schemas evolve, older skills and plugins accumulate deprecated tags, broken syntax, and obsolete configuration options.

This skill provides non-destructive **Diagnostics & Idempotent Auto-Healing** across the workspace.

---

## 4-Stage Doctor Auto-Fix Pipeline (四阶体检自愈工作流)

```
[Stage 1: Syntax & Legacy Schema Scanning (语法扫描与废弃识别)]
  - Scan all `SKILL.md` and plugin manifest files (`plugin.json`, `mcp.json`)
  - Cross-reference against the active Deprecation Registry
         ↓
[Stage 2: Deprecation Rules Engine (废弃规则引擎对齐)]
  - Rule 1: `tools:` or `tools_required:` -> auto-rewrite to `allowed-tools:`
  - Rule 2: `requirements:` -> auto-rewrite to `requires:`
  - Rule 3: Obsolete sandbox permissions (`root`, `privileged`) -> downgrade to `required_permissions: ["all"]`
  - Rule 4: Trailing slash or missing quote syntax errors in YAML frontmatter
         ↓
[Stage 3: Safety Backup & Diff Preview (安全备份与差异预览)]
  - Automatically create an atomic backup file (`{filename}.bak.YYYYMMDD`)
  - Generate unified markdown diff for user inspection before touching disks
         ↓
[Stage 4: Idempotent Patching & Schema Validation (幂等修复与自检验证)]
  - Write normalized YAML and JSON declarations
  - Re-run linter and schema validator to guarantee 100% compliant state
```

---

## Output Contract & Template (`docs/audits/doctor-fix-report.md`)

```markdown
# 插件语法体检与一键自愈报告 (Doctor Fix Report)

- **体检对象**: 工作区内 18 个技能与插件配置文件
- **检测模式**: `--fix` (自动修复已生效)
- **总体健康度**: 提升前 **68%** ➔ 修复后 **100%** (0 处已知废弃语法)

---

## 一、废弃语法定位与修复记录 (Remediation Ledger)

| 目标文件路径 | 检出废弃项 | 修复动作 | 备份文件 |
|---|---|---|---|
| `assets/skills/web-scraper/SKILL.md` | `tools: [curl]` | 重命名为 `allowed-tools: [bash_code_execute_tool]` | `*.bak.20260910` |
| `plugins/notion-sync/plugin.json` | `requirements.env` | 归一化为 `requires.env` 数组 | `*.bak.20260910` |

---

## 二、关键差异比对 (Sample Diff Preview)

```diff
--- a/assets/skills/web-scraper/SKILL.md
+++ b/assets/skills/web-scraper/SKILL.md
@@ -5,2 +5,2 @@
-tools:
-  - curl
+allowed-tools:
+  - bash_code_execute_tool
```

---

## 三、后续建议与不变量保障
- 所有备份文件已妥善归档，若需回滚可执行一键还原命令。
- 工作区当前所有 Frontmatter 均已符合 Agent Skills 1.0 SSOT 统一规范。
```

---

## Operational Safeguards
- **Mandatory Atomic Backups**: Never overwrite an existing configuration without writing a `.bak` copy first.
- **Idempotence Guarantee**: Running this skill multiple times in succession must produce identical results with zero additional diffs.
