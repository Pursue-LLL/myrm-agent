---
name: meeting-minutes-extractor
description: "Extract structured meeting minutes, key decisions, attendee commitments, and follow-up deadlines from raw transcripts or audio notes, with optional calendar and workspace connector synchronization."
version: "1.0.0"
category: "productivity"
tags:
  - meeting-minutes
  - audio-transcript
  - action-items
  - productivity
  - connector-preflight
oauth_issuer: google_workspace
required_oauth_issuers:
  - google_workspace
required_mcp_servers:
  - notion
  - linear
allowed-tools:
  - file_write_tool
  - file_read_tool
---

# Meeting Minutes Extractor & Action Items Sync (智能会议纪要与待办同步技能)

## Overview

A dedicated skill for transforming raw audio transcripts, rough scratchpad notes, or multi-party conversation logs into structured, executive-grade **Meeting Minutes (`docs/meetings/YYYY-MM-DD-{topic}.md`)**.

It enforces:
1. **Connector Dependency Declaration (连接器前置声明)**: Explicitly declares required OAuth issuers (`google_workspace`) and MCP servers (`notion`, `linear`) in frontmatter so users know prerequisite connections in advance.
2. **Minimal-Mount Discipline (最小装配纪律)**: Does NOT blindly mount all external tools into the session. If connectors are unavailable or unneeded for simple markdown note taking, it degrades gracefully to a zero-cloud, pure-local file workflow without failing.
3. **Structured 5-Part Minutes Schema**: Executive Summary, Attendees & Absences, Key Decisions, Discussion Topics, and Action Items Table.

---

## Connector Preflight & Graceful Degradation (连接器预检与优雅降级)

| Connector | Frontmatter Key | Purpose | Degradation if Disconnected |
|---|---|---|---|
| **Google Calendar** | `required_oauth_issuers: [google_workspace]` | Schedule follow-up meetings & calendar invite blocks | Output markdown ICS snippet for manual import |
| **Notion** | `required_mcp_servers: [notion]` | Sync minutes directly to team meeting wiki | Save local `docs/meetings/*.md` file |
| **Linear / Jira** | `required_mcp_servers: [linear]` | Automatically create follow-up task tickets | Output structured checklist for manual ticket creation |

---

## 5-Part Meeting Minutes Contract

Every synthesized meeting record must adhere to this template:

```markdown
# 会议纪要: [会议主题]

- **会议日期**: YYYY-MM-DD HH:mm
- **主持人**: [姓名]
- **记录人**: [姓名]
- **参会人员**: [姓名A, 姓名B, 姓名C]
- **缺席人员**: [姓名D (请假)]

---

## 一、核心结论与决议速览 (Executive Summary & Key Decisions)
1. **[决议 1]**: 经过评审，一致同意 ...
2. **[决议 2]**: 暂缓实施 ...，预计下个双周重新评审。

---

## 二、议题详细讨论 (Discussion Topics)

### 议题 1: [业务/技术议题名称]
- **背景与分歧**: ...
- **核心论点**:
  - [发言人 A]: 建议采用方案 X，理由是 ...
  - [发言人 B]: 指出方案 X 存在的性能风险 ...
- **最终对齐结果**: ...

---

## 三、待办行动项追踪 (Action Items & Owner Matrix)

| 序号 | 待办任务描述 | 责任人 | 截止时间 (DDL) | 同步系统 | 状态 |
|---|---|---|---|---|---|
| 1 | 交付接口设计规范草案 | @张三 | YYYY-MM-DD | Notion / 本地 | 进行中 |
| 2 | 完成基准压测与数据对齐 | @李四 | YYYY-MM-DD | Linear / 本地 | 待启动 |

---

## 四、下次跟进时间 (Next Check-in)
- 预计于 **YYYY-MM-DD HH:mm** 召开进展同步会。
```

---

## Minimal-Mount & Anti-Dilution Rules
- **No Blanket Tool Expansion**: Never ask the user to enable all MCP tools at once. Only prompt for connection if the user explicitly asks to sync with external SaaS platforms.
- **Pure Local First**: Even with zero connected OAuth or MCP services, this skill functions at 100% fidelity for text and markdown generation.
