# app/config/subagents/core


---

## 架构概述

内置子 Agent 类型的 **YAML 数据目录**（无 Python 代码）。每个文件对应一种子 Agent，字段规范见 [../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 |
|------|------|------|
| `adversarial-reviewer.yaml` | 数据 | 对抗性审查子 Agent（cron post-run verifier 内部使用，不进入用户可选目录） |
| `browser.yaml` | 数据 | 浏览器子 Agent（8× `browser_*_tool` SSOT 名）；主 Agent 开 browser 时 server 自动绑定 `browser-automation` peripheral skill |
| `structure-planner.yaml` | 数据 | 结构化交付物大纲与逻辑架构设计子 Agent（MECE/金字塔原理/论点与依赖矩阵） |
| `layout-designer.yaml` | 数据 | 结构化交付物视觉版式与布局设计子 Agent（幻灯片网格/主题配色/图表选型） |
| `format-verifier.yaml` | 数据 | 结构化交付物排版规范与格式审计子 Agent（反文字墙/公式完整性/标题层级；只读，无 bash） |
| `explore.yaml` | 数据 | 极速只读探索型子 Agent（白名单只读工具 file_read/grep/glob、黑名单物理裁撤剥离写/命令执行工具、工作区 read_only_sandbox、零主对话上下文污染、结构化 Markdown 证据引用输出） |
