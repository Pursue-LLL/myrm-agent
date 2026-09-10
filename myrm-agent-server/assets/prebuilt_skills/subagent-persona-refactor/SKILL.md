---
name: subagent-persona-refactor
description: >-
  Audit historical agent execution transcripts and multi-turn session logs to diagnose
  bottlenecks, instruction drift, and tool confusion. Systematically refactors monolithic fat agents
  into modular, single-responsibility subagent persona matrices with tight tool boundaries and exportable YAML specifications.
version: 1.0.0
category: engineering
tags:
  - transcript-audit
  - subagent-refactor
  - persona-matrix
  - bottleneck-diagnosis
  - tool-boundary
  - single-responsibility
  - 子智能体人设重构
  - 会话审计
allowed-tools: file_write_tool file_read_tool bash_code_execute_tool
contract:
  steps:
    - 1. Transcript & Trace Ingestion (Parse session logs for tool call distributions, retry loops, and failure spikes)
    - 2. Bottleneck & Drift Diagnostics (Detect fat agent anti-patterns, circular retries, and context pollution)
    - 3. Role Specialization & Persona Matrix Synthesis (Decompose monolithic tasks into SRP subagents with precise tool boundaries)
    - 4. Production Agent Spec Compilation (Export standardized subagent YAML profiles and inter-agent handoff contracts)
  potential_traps:
    - description: Retaining fat monolithic agents that attempt planning, coding, and testing in a single bloated system prompt
      mitigation: Follow the skill SOP and verification_steps before proceeding; abort on ambiguity and surface the risk to the user
      severity: medium
    - description: Granting unrestricted tool access to subagents instead of enforcing minimal necessary privilege boundaries
      mitigation: Follow the skill SOP and verification_steps before proceeding; abort on ambiguity and surface the risk to the user
      severity: medium
    - description: Omitting explicit handoff payload schemas causing silent state loss between collaborating subagents
      mitigation: Follow the skill SOP and verification_steps before proceeding; abort on ambiguity and surface the risk to the user
      severity: medium
    - description: Over-fragmenting workflows into trivial 1-line subagents creating severe orchestration latency overhead
      mitigation: Follow the skill SOP and verification_steps before proceeding; abort on ambiguity and surface the risk to the user
      severity: medium
  verification_steps:
    - Verify all diagnostic metrics include failure frequencies, retry counts, and tool confusion rates
    - Confirm synthesized subagent profiles define explicit In-Scope and Out-of-Scope boundaries
    - Ensure generated YAML configurations pass Myrm agent template validation schemas
  success_criteria:
    - High-cohesion, low-coupling subagent persona matrix that eliminates execution deadlocks and minimizes token bloat
---

# Historical Transcript Workflow Auditor & SubAgent Persona Refactor (历史会话工作流审计与子智能体人设重构)

## Bash execution contract

When calling `bash_code_execute_tool`, always pass **`reason`** (≥10 characters: why this command runs) and **`command`**. Put `reason` first.


## Overview

A dedicated skill for multi-agent system architects and LLM ops engineers to analyze real-world session transcripts,
identify operational bottlenecks (excessive retries, context bloat, hallucinated tool calls), and refactor monolithic "fat agents"
into high-performance, single-responsibility **SubAgent Persona Networks**.

Inspired by production postmortems where single general-purpose agents fail after 15+ turns due to cognitive overload,
this skill applies the **Single Responsibility Principle (SRP)** to LLM agent orchestration.

---

## 4-Stage Transcript-to-SubAgent Refactor Pipeline (四阶会话审计与人设重构流水线)

```
Stage 1: Trace Ingestion & Statistical Profiling (日志摄取与行为频次统计)
   ├── Aggregate tool calls, retry frequencies, execution duration, and error locations
   └── Compute context token consumption trajectories across conversation turns
Stage 2: Bottleneck & Anti-Pattern Diagnosis (瓶颈与人设漂移根因诊断)
   ├── Detect "Fat Agent Anti-Pattern" (agent trying to research, design, code, test simultaneously)
   ├── Identify "Tool Confusion" (agent invoking invalid parameters or conflicting tools)
   └── Pinpoint "Death Loops" (repeated tool failures without strategy adaptation)
Stage 3: SubAgent Persona Matrix Synthesis (单一职责子智能体人设矩阵重构)
   ├── Partition tasks by cognitive domain: Research, Planning, Execution, Verification
   ├── Draft specialized System Prompts with strict In-Scope / Out-of-Scope boundaries
   └── Enforce Minimal Privilege Tool Boundaries (e.g. read-only for planners, write-only for coders)
Stage 4: Spec Compilation & Handoff Schema (生产级配置编译与上下文交接契约)
   ├── Generate production-ready Myrm Agent YAML specifications
   └── Define typed Handoff Payload Schemas for seamless zero-loss state transfer
```

---

## 1. Diagnostic Indicators & Anti-Pattern Taxonomy (诊断指标与反模式分类)

| Metric / Anti-Pattern | Diagnostic Threshold | Root Cause | Refactoring Prescription |
|---|---|---|---|
| **Fat Agent Bloat** | Single prompt > 1500 words or > 8 tool bindings | The agent is expected to be a generalist super-brain | Split into specialized SubAgents: Planner, Builder, Auditor |
| **Tool Confusion Rate** | > 2 invalid tool invocations per 10 turns | Too many similar tools exposed in the same context window | Narrow tool space to <= 4 tools per specialized persona |
| **Retry Storm (Death Loop)**| >= 3 consecutive identical tool failures | Agent lacks recovery heuristics or domain knowledge | Introduce Verification SubAgent with explicit rollback rules |
| **Instruction Drift** | Goal abandonment after Turn 8 | Long-context distraction and conflicting requirements | Isolate long-context tasks inside dedicated ephemeral subagents |

---

## 2. Standard SubAgent Persona Matrix (标准四维子智能体人设矩阵)

When refactoring a complex monolithic workflow, decompose it into this decoupled topology:

```
[Main Dispatcher / Orchestrator]
       │
       ├──► 1. Research Specialist (搜集与前置调研: Read-Only Web/File Tools)
       ├──► 2. Architecture Planner (架构与规格规划: Diagram/Design Tools, No Direct Code Write)
       ├──► 3. Code Implementer (工程编码工匠: File Edit/Write Tools, Sandboxed Bash Execution)
       └──► 4. Quality & Security Guard (质量与安全门禁: Linter, Test Runner, Read-Only Auditing)
```

---

## 3. Deliverable Specification: SubAgent YAML Profile (`subagents/{role}.yaml`)

Every refactored persona must produce a concrete, production-grade specification:

```yaml
id: "quality_verifier"
name: "代码质量与门禁审计专家"
version: "1.0.0"
category: "engineering"
description: "专注于静态语法检查、测试覆盖率验收与安全合规门禁，杜绝未经验证的代码提交"

system_prompt: |
  You are an uncompromising Code Quality and Verification Gatekeeper.
  Your SOLE mission is to verify implementation correctness through physical test execution.
  
  BOUNDARIES:
  - In-Scope: Running linters, executing pytests, asserting zero regression, auditing diffs.
  - Out-of-Scope: NEVER rewrite business logic from scratch; delegate fixes back to Implementer.

allowed_tools:
  - bash_code_execute_tool
  - file_read_tool
  - read_lints_tool

handoff_contract:
  input_schema:
    changed_files: "list[str]"
    test_command: "str"
  output_schema:
    status: "PASSED | FAILED"
    failure_logs: "list[str] | null"
    actionable_remedies: "list[str] | null"
```
