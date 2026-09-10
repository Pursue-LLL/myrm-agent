---
name: github-skill-installer-auditor
description: "Zero-config dynamic installer and sandbox security auditor for mounting external community skills directly from GitHub repositories without server restarts."
version: "1.0.0"
category: "engineering"
tags:
  - github-installer
  - dynamic-skills
  - sandbox-audit
  - security-gate
  - supply-chain
allowed-tools:
  - file_write_tool
  - file_read_tool
  - bash_code_execute_tool
---

# GitHub URL Zero-Config Dynamic Skill Installer & Sandbox Auditor (GitHub 技能零配置动态安装与沙箱审计技能)

## Overview

A dedicated infrastructure skill for safely importing, auditing, and dynamically mounting third-party skills directly from public or private GitHub repository URLs (e.g. `https://github.com/org/repo-skill`).

It eliminates the severe supply chain security hazard of blindly running unverified external agent code by establishing a mandatory **4-Tier Sandbox Security Gate**.

---

## The 4-Tier Sandbox Security Gate (四重沙箱安全门禁)

```
[Tier 1: Ephemeral Shallow Clone (隔离区浅克隆)]
  - Execute depth=1 git clone inside an ephemeral sandbox directory (`.myrm/staging/{hash}`)
  - Enforce timeout <= 30s and payload size limit <= 10MB
         ↓
[Tier 2: Static Threat & Anti-Pattern Radar (静态威胁与反模式雷达)]
  - AST / Regex scan for prohibited syscalls: `rm -rf /`, `mkfs`, `/etc/shadow`, `~/.ssh`
  - Scan for plaintext hardcoded API keys, tokens, and unauthorized telemetry endpoints
  - Verify frontmatter schema compliance (`name`, `description`, `allowed-tools`)
         ↓
[Tier 3: Capability & Dependency Preflight (能力契约与依赖预检)]
  - Check for required external CLI binaries (`curl`, `ffmpeg`, `pandoc`)
  - Check for required python extras (`openpyxl`, `bs4`, `requests`)
  - Calculate security score (0-100); require >= 85 for zero-prompt auto-mount
         ↓
[Tier 4: Hot Mount & Audit Traceability (无重启热装载与审计留痕)]
  - Move validated bundle to `.myrm/skills/{skill_name}`
  - Register in-memory skill catalog without restarting backend server
  - Output an audit receipt recording git commit SHA, scan timestamp, and findings
```

---

## Audit Receipt Contract & Template (`docs/audits/skill-install-{name}.md`)

```markdown
# 技能动态安装与安全审计回执 (Skill Installation Audit Receipt)

- **技能名称**: `custom-scraper`
- **源仓库地址**: `https://github.com/example-org/custom-scraper`
- **目标分支 / Commit SHA**: `main` (`7a8f9c2`)
- **安全评级**: **95 / 100** (PASS · 极低风险)

---

## 一、静态代码威胁审计清单 (Static Threat Matrix)

| 扫描维度 | 审计规则 | 命中项 | 状态 |
|---|---|---|---|
| 文件破坏性指令 | 禁止高危 `rm -rf`, `format`, `dd` 等磁盘指令 | 0 处 | ✅ 通过 |
| 凭据与敏感凭证 | 检索环境变量偷取、私钥目录访问 (`~/.ssh`, `id_rsa`) | 0 处 | ✅ 通过 |
| 未授权网络外联 | 检索非白名单域名硬编码回传 | 0 处 | ✅ 通过 |
| Frontmatter 契约 | 严格检查 `name`, `allowed-tools` 格式 | 符合规范 | ✅ 通过 |

---

## 二、运行环境契约兼容性 (Compatibility)
- **依赖工具项**: `file_read_tool`, `file_write_tool` (宿主环境原生支持)
- **可选依赖项**: `beautifulsoup4` (沙箱已具备)

---

## 三、挂载状态
- **安装路径**: `.myrm/skills/custom-scraper/`
- **生效模式**: 零重启热挂载 (Hot-mounted)
- **生效会话**: 当前会话及后续新会话即时可用
```

---

## Hard Invariants & Circuit Breakers
- **Immediate Discard on Critical Findings**: Any appearance of unquoted root deletions or base64-encoded shell payloads triggers instant sandbox termination and a P0 security alert to the user.
- **Pure Sandboxed Staging**: Third-party code is strictly forbidden from executing outside `.myrm/staging/` before passing Tier 3 preflight.
