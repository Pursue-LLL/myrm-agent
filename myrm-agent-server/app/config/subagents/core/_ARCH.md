# app/config/subagents/core


---

## 架构概述

内置子 Agent 类型的 **YAML 数据目录**（无 Python 代码）。每个文件对应一种子 Agent，字段规范见 [../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 |
|------|------|------|
| `search.yaml` | 数据 | 搜索类子 Agent 默认定义 |
| `browser.yaml` | 数据 | 浏览器类子 Agent 默认定义 |
| `analysis.yaml` | 数据 | 分析类子 Agent 默认定义 |
| `coding.yaml` | 数据 | 编码类子 Agent 默认定义（含外部 Agent 委派能力） |
