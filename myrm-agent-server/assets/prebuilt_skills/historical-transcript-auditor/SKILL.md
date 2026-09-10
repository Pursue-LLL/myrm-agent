---
name: historical-transcript-auditor
description: >-
  Scan, audit, and diagnose operational bottlenecks across historical agent execution logs,
  transcripts, and multi-turn session records. Pinpoint tool retry loops, prompt drift,
  redundant tool thrashing, and subagent persona misalignments, providing actionable
  persona refactoring blueprints and optimized system prompt configurations.
version: 1.0.0
category: enterprise-ops
tags:
  - transcript-audit
  - session-analysis
  - subagent-refactor
  - prompt-engineering
  - bottleneck-diagnosis
  - codex-logs
  - 日志审计
  - 人设重构
  - 瓶颈排查
allowed-tools: file_read_tool file_write_tool bash_code_execute_tool
contract:
  steps:
    - "Phase 1: Multi-Session Ingestion & Log Normalization — Scan session transcripts, normalize events (turns, tool calls, latencies, errors, token usage)"
    - "Phase 2: Bottleneck & Failure Pattern Clustering — Detect repetitive retry loops, circuit-breaker triggers, high-friction tool thrashing, and prompt drift"
    - "Phase 3: SubAgent Persona & Boundary Gap Diagnosis — Evaluate whether subagents suffered from vague responsibilities, excessive tool scope, or weak negative constraints"
    - "Phase 4: Persona Refactoring Blueprint & System Prompt Optimization — Output refactored YAML profile specs, tightened boundary guardrails, and before/after metrics"
  potential_traps:
    - description: "Analyzing single session outliers instead of aggregate multi-turn statistical failure clusters"
      mitigation: "Always group failures across at least 10+ historical runs or declare sample size limitations"
      severity: high
    - description: "Suggesting broad persona prompt bloat instead of precise tool exclusion and negative guardrails"
      mitigation: "Prioritize shrinking tool action space and adding explicit MECE negative boundaries over adding more prompt rules"
      severity: high
    - description: "Overlooking circuit breaker and timeout root causes in tool loops"
      mitigation: "Explicitly trace latency histograms and repetitive identical tool arguments before modifying system prompts"
      severity: medium
  verification_steps:
    - step_id: audit_report_completeness
      description: "Ensure the generated audit report includes Failure Taxonomy, Tool Friction Matrix, and SubAgent Refactor Specs"
      validation_method: "Inspect output markdown for all mandatory report sections"
      is_required: true
    - step_id: valid_refactored_yaml
      description: "Verify that all proposed SubAgent Persona YAML snippets conform to Myrmidon Agent Profile schema"
      validation_method: "Validate YAML parsing and mandatory keys (name, role, system_prompt, allowed_tools)"
      is_required: true
  success_criteria: "Historical transcripts are aggregated and mined into an actionable bottleneck audit report with validated, high-efficiency SubAgent persona refactor configurations."
  estimated_duration_seconds: 300
---

# Historical Transcript Workflow Auditor & SubAgent Persona Refactor

## Bash execution contract

When calling `bash_code_execute_tool`, always pass **`reason`** (≥10 characters: why this command runs) and **`command`**. Put `reason` first.


## Overview

When enterprise AI agents scale to production, the primary source of failure is rarely base model intelligence—it is **subagent persona degradation and workflow thrashing**:
- Subagents assigned vague overlapping responsibilities fight over identical files.
- Coding and research agents repeatedly invoke failed tools in tight retry loops without pivoting.
- Excessive tool permissions trigger hallucinated invocations and wasted context tokens.

The **Historical Transcript Workflow Auditor** systematically inspects collections of execution transcripts, clusters operational bottlenecks, diagnoses root causes in subagent personas, and outputs hardened system prompts and boundary configurations.

---

## The 4-Phase Operational Workflow

### Phase 1: Multi-Session Ingestion & Log Normalization
1. Discover and ingest conversation transcripts from `agent-transcripts/`, task logs, or exported JSONL history.
2. Extract standardized turn-level telemetry:
   - Total turns per task
   - Tool invocation frequencies and error rates
   - Repetitive call signatures (identical tool + identical args)
   - Step latency and token consumption per turn

### Phase 2: Bottleneck & Failure Pattern Clustering
Group historical friction points into the **4 Classic Failure Typologies**:

| Failure Typology | Symptoms | Root Cause |
| --- | --- | --- |
| **Tool Thrashing (工具空转)** | 5+ consecutive calls to `read` / `grep` without file edits | Missing search termination heuristics or fuzzy match failure |
| **Persona Conflict (人设冲突)** | Subagent A edits code; Subagent B immediately reverts or rewrites | Unclear MECE boundary between architect and implementer |
| **Prompt Drift (提示词漂移)** | Assistant outputs conversational pleasantries instead of structured outputs | System prompt lacks output contract schemas and negative constraints |
| **Hallucinated Tooling (工具误用)** | Agent calls non-existent APIs or ignores declared parameter schemas | Over-broad tool exposure diluting the attention distribution |

### Phase 3: SubAgent Persona & Boundary Gap Diagnosis
For each underperforming agent profile:
- **Audit Tool Action Space**: Remove all tools the agent did not actively succeed with in 90% of tasks.
- **Audit Responsibility Scope**: Define exact inputs, allowed transformations, and forbidden actions (Negative Guardrails).
- **Audit Collaboration Protocol**: Specify unambiguous handoff signals (e.g. "Deliver outline in `specs/`, do not write production code").

### Phase 4: Persona Refactoring Blueprint & System Prompt Optimization
Generate concrete, drop-in replacement Agent Profile YAML files:

```yaml
# Refactored SubAgent Profile Specification
id: refactored_specialist_agent
name: "Refactored Domain Specialist"
role: "Strict Boundary Execution Specialist"
system_prompt: |
  You are an execution specialist with a narrow, high-precision scope.
  
  CORE MISSION:
  Execute [Target Domain] actions strictly adhering to input specs.
  
  NEGATIVE CONSTRAINTS (HARD GATES):
  1. DO NOT modify any architecture documentation or spec files.
  2. DO NOT retry an identical failed tool call more than twice; pivot or ask clarification.
  3. DO NOT output conversational filler; return only structured artifacts.
allowed_tools:
  - file_read_tool
  - file_edit_tool
```

---

## Deliverable Quality Checklist

Before finalizing the audit and persona refactor:
- [ ] Are failure counts backed by physical transcript evidence (session IDs, line numbers, error traces)?
- [ ] Does every refactored subagent specify explicit **Negative Constraints (禁止事项)**?
- [ ] Is the tool action space strictly pruned to minimal necessary tools (Anti-Dilution)?
- [ ] Are all suggested YAML profiles syntactically valid and ready for hot mounting?
