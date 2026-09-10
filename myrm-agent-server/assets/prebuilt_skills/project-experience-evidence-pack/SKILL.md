---
name: project-experience-evidence-pack
description: "Assemble a structured, audit-grade 6-step project experience evidence pack from raw requirements, v0 drafts, execution traces, and verified outcomes."
version: "1.0.0"
category: "engineering"
tags:
  - project-experience
  - evidence-pack
  - audit
  - postmortem
  - case-study
allowed-tools:
  - file_write_tool
  - file_read_tool
---

# Project Experience 6-Step Evidence Pack Wizard (项目实战经验六步证据包向导)

## Overview

A dedicated skill for distilling end-to-end task execution traces, initial requirements, v0 prototypes, verification logs, and learnings into an audit-grade **6-Step Project Experience Evidence Pack (`evidence-pack.md`)**.

This prevents "empty boast case studies" by enforcing verifiable, objective physical evidence at every stage of the project lifecycle.

---

## The 6-Step Evidence Architecture (六步证据链标准体系)

When synthesizing or exporting a project case study, strictly structure the output into the following 6 verifiable stages:

```
Step 1: Original Intent & Constraints (原始诉求与核心边界)
   ↓
Step 2: v0 Initial Design / Prototype (v0 首稿方案与基线设计)
   ↓
Step 3: Execution Bottlenecks & Failure Traces (执行瓶颈与真实失败轨迹)
   ↓
Step 4: Root-Cause Analysis & Fix Justifications (根本原因与修正依据)
   ↓
Step 5: Verifiable Physical Proof & Benchmark (实测物理证据与指标验收)
   ↓
Step 6: Crystallized Experience & Invariant Lessons (经验沉淀与防复发不变量)
```

---

## Detailed Specification for Each Step

### Step 1: Original Intent & Constraints (原始诉求与核心边界)
- **User Original Prompt**: Exact raw objective text without LLM beautification.
- **Explicit Invariants & Budget**: Stated deadlines, token budgets, forbidden paths, and strict compliance constraints.
- **Target Deliverable Matrix**: Defined deliverables (code, schemas, documents, tables).

### Step 2: v0 Initial Design / Prototype (v0 首稿方案与基线设计)
- **Initial Architecture / Mock**: The initial proposal or v0 baseline.
- **Identified Latent Vulnerabilities**: Architectural trade-offs, potential single points of failure, or unverified assumptions in v0.

### Step 3: Execution Bottlenecks & Failure Traces (执行瓶颈与真实失败轨迹)
- **Error Logs / Test Failures**: Concrete tool error outputs, stack traces, compiler errors, or lint violations.
- **Execution Trace Highlights**: Key events from `ExecutionTraceTimeline` (e.g. timeout, memory leak, edge case regression).

### Step 4: Root-Cause Analysis & Fix Justifications (根本原因与修正依据)
- **First-Principles Diagnosis**: Explaining *why* the failure happened rather than just describing symptoms.
- **Comparative Diff Rationale**: Explaining why Alternative B was selected over Alternative A, supported by architectural principles.

### Step 5: Verifiable Physical Proof & Benchmark (实测物理证据与指标验收)
- **Deterministic Test Results**: Exact command run (e.g., `run-pytest-safe.sh tests/...`) with exit code `0` and test count.
- **Metric Differential Table**: Before vs. After metrics (latency, memory footprint, bundle size, token consumption).

### Step 6: Crystallized Experience & Invariant Lessons (经验沉淀与防复发不变量)
- **Golden Rules**: 2-3 universal axioms learned from this engagement.
- **Automated Guardrail Addition**: New linter rules, CI tests, or runtime assertions introduced to permanently prevent regression.

---

## Deliverable Markdown Contract

Output file naming convention: `docs/project-experience/{project-slug}-evidence-pack.md` or as an inline structured artifact.

```markdown
# [Project Name] 实战经验六步证据包

## 1. 原始诉求与核心边界
- 原始任务指令: ...
- 关键约束条件: ...

## 2. v0 首稿方案与基线设计
- 初版设计概述: ...
- 初始架构简图 / 代码结构: ...

## 3. 执行瓶颈与真实失败轨迹
- 遇到的物理阻断 / 错误日志:
  ```
  [Error Code / Trace Snippet]
  ```
- 失败归因排查: ...

## 4. 根本原因与修正依据
- 根因分析: ...
- 关键重构对比 (Diff / 方案替代): ...

## 5. 实测物理证据与指标验收
- 自动化测试与物理验证输出:
  ```
  [Test Runner Output with 100% Passed]
  ```
- 关键性能指标对比表:
  | 指标项 | 优化前 | 优化后 | 提升幅度 | 验证方式 |

## 6. 经验沉淀与防复发不变量
- 核心工程教训: ...
- 新增防复发自动化门禁: ...
```
