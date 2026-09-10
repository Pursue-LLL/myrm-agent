---
name: transcript-workflow-auditor
description: "Audit hundreds of historical agent session transcripts and execution traces to identify retry loops, tool rejections, and context bloat, refactoring sub-agent persona prompts and negative constraints."
version: "1.0.0"
category: "operations"
tags:
  - transcript-audit
  - persona-refactor
  - execution-traces
  - bottleneck-diagnosis
  - guardrails
allowed-tools:
  - file_write_tool
  - file_read_tool
---

# Historical Transcript Workflow Auditor & Sub-Agent Persona Refactor (历史会话工作流审计与子智能体人设重构技能)

## Overview

A specialized meta-engineering skill for auditing real-world execution transcripts, trace timelines, and tool call logs across hundreds of sessions.

It identifies the 3 cardinal execution pathologies:
1. **Endless Retry Loops (无限重试死循环)**: Agents failing a tool call with the exact same invalid parameters 3+ times.
2. **Tool Rejections & Permission Failures (工具拒绝与权限越权)**: Shell execution blocked by security filters or non-existent CLI flags.
3. **Persona Drift & Wall-of-Text Bloat (人设漂移与冗余废话)**: Sub-agents hallucinating out-of-scope tasks or dumping 2000-word essays when single-line answers were requested.

It synthesizes an actionable **Transcript Audit Report (`docs/audits/transcript-audit-YYYY-MM.md`)** and refactors the target Sub-Agent Persona System Prompts with hardened negative constraints.

---

## 4-Stage Audit & Refactoring Pipeline (四阶审计与重构流水线)

```
Stage 1: Trace Harvesting & Bottleneck Clustering (会话日志归集与聚类)
   ├── Ingest raw session transcripts from `agent-transcripts/` or `.myrm/traces/`
   └── Cluster failure modes by frequency, tool name, and exit codes
Stage 2: Three-Malady Pathological Diagnosis (三大病灶定量诊断)
   ├── Metric 1: Tool Repeat Ratio (TR = duplicate tool calls / total calls)
   ├── Metric 2: Security Friction Index (SFI = blocked commands / total shell calls)
   └── Metric 3: Output Efficiency Ratio (OER = tangible artifacts / total tokens spent)
Stage 3: Sub-Agent Persona System Prompt Hardening (人设规约精准重构)
   ├── Add surgical Negative Rules (e.g., "NEVER re-read file X without changing offset")
   ├── Inject Explicit Failure Fast Protocols (e.g., "If curl returns 404, STOP immediately")
   └── Narrow allowed tool scopes to eliminate unnecessary tool description overhead
Stage 4: Regression Test & Verification Gate (重构验收门禁)
   └── Run replay simulations against the historically failed turns to confirm 0% regression
```

---

## Output Contract & Template (`docs/audits/transcript-audit-report.md`)

```markdown
# 智能体会话日志体检与人设重构审计报告

- **审计样本总量**: 250 次完整会话 (共计 4,820 个 Tool Calls)
- **目标子智能体**: `code-debugger` / `research-assistant`
- **综合健康度得分**: **74 / 100** (警告级)

---

## 一、高频故障与低效瓶颈分布 (Cardinal Pathologies)

| 故障特征 | 发生频次 | 浪费 Token 估算 | 典型案例 Session ID |
|---|---|---|---|
| 工具参数格式错误反复重试 | 42 次 | ~180,000 | `trace-8309-4428` |
| 破坏性或只读越权命令被拦截 | 18 次 | ~65,000 | `trace-9912-1102` |
| 闲聊发散与人设职责漂移 | 29 次 | ~110,000 | `trace-5541-8891` |

---

## 二、子智能体人设重构方案 (Refactored Persona Prompt)

### 原始缺陷 Prompt:
> "你是一个全能的代码调试助手，负责帮助用户修复所有问题。"

### 经过实证重构后的生产级 Hardened Prompt:
> "你是一个专注的单文件语法与逻辑调试助手。
> 
> 【硬性负向规约】:
> 1. 遇到同一错误连续出现 2 次时，绝对禁止以相同参数第 3 次调用该工具；必须立即调用 `ask_question_tool` 抛出具体阻塞事实。
> 2. 严禁执行任何重命名、删除或全局依赖安装命令；只允许读写指定路径下的单文件。
> 3. 回复中严禁包含无关客套话，输出必须严格以【根因诊断】与【验证结果】两段呈现。"

---

## 三、防复发回归验证数据
- **重放验证通过率**: **100%** (20 个历史死循环测试用例全部在 1 轮内精准截断或修复)。
```

---

## Operational Safeguards
- **Zero Privacy Leakage**: Strictly redact all user tokens, IP addresses, and private passwords before outputting audit reports.
- **Evidence-First**: Every refactored prompt rule must cite at least one concrete session failure trace.
