# app/config/subagents/core


---

## 架构概述

内置子 Agent 类型的 **YAML 数据目录**（无 Python 代码）。每个文件对应一种子 Agent，字段规范见 [../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 |
|------|------|------|
| `adversarial-reviewer.yaml` | 数据 | 对抗性审查子 Agent（只读、Devil's Advocate 协议、结构化 JSON 输出） |
| `browser.yaml` | 数据 | 浏览器子 Agent（8× `browser_*_tool` SSOT 名）；主 Agent 开 browser 时 server 自动绑定 `browser-automation` peripheral skill |
| `analysis.yaml` | 数据 | 分析子 Agent（`memory_*_tool` SSOT 名） |
| `coding.yaml` | 数据 | 编码类子 Agent（`grep_tool`/`glob_tool`/file/bash；深度代码智能靠用户 MCP） |
| `deep-audit.yaml` | 数据 | 深度安全审计子 Agent（全量并发扫描、专注逻辑漏洞、只读模式） |
| `search.yaml` | 数据 | 搜索类子 Agent 默认定义 |
