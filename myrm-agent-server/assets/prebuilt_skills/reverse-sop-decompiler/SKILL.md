---
name: reverse-sop-decompiler
description: >-
  Reverse-engineer, decompile, and formalize standard operating procedures (SOPs)
  from unstructured customer service dialogues, audio transcripts, incident triage histories,
  and operations chat logs. Synthesizes executable Mermaid decision trees and ready-to-run
  Agent Profile YAML definitions.
version: 1.0.0
category: enterprise-ops
tags:
  - sop
  - decompiler
  - workflow
  - process-mining
  - business-automation
  - mermaid
  - agent-profile
  - 流程反编译
  - 决策树提取
  - 数字员工上岗
allowed-tools: file_read_tool file_write_tool
contract:
  steps:
    - "Phase 1: Multi-Turn Dialogue Ingestion & Noise Pruning — Strip social pleasantries, identify causal action-resolution pairs"
    - "Phase 2: Decision Node & Branch Mining — Extract conditional gates (if/else), triage policies, required tools, and fallback escalations"
    - "Phase 3: Formal SOP Specification & Mermaid Tree Generation — Draft Markdown SOP document and compile graphical Mermaid flowchart"
    - "Phase 4: Agent Profile YAML Export — Package the extracted SOP into a self-contained, deployable Agent Profile specification"
  potential_traps:
    - description: "Overfitting on exceptional or rare single-case failures leading to overly convoluted decision trees"
      mitigation: "Strict separation between Main Flow (80% Happy Path) and Exception Branches (Edge Cases)"
      severity: high
    - description: "Synthesizing vague step descriptions that human or AI agents cannot programmatically execute"
      mitigation: "Every step must declare explicit preconditions, input parameters, action tool/API, and exit criteria"
      severity: high
    - description: "Omitting human escalation paths when confidence is low"
      mitigation: "Mandate an explicit HITL Escalation Node whenever a decision branch encounters an unresolvable state"
      severity: medium
  verification_steps:
    - step_id: mermaid_syntax_valid
      description: "Ensure generated Mermaid decision tree graph TD renders without syntax errors"
      validation_method: "Inspect Mermaid block syntax for closed brackets and valid edge definitions"
      is_required: true
    - step_id: agent_profile_valid
      description: "Confirm exported Agent Profile YAML contains valid role, prompt, and tool definitions"
      validation_method: "Check YAML syntax and required fields"
      is_required: true
  success_criteria: "An unstructured operational transcript is fully decompiled into a verified SOP document, visual Mermaid chart, and deployable Agent Profile."
  estimated_duration_seconds: 360
---

# Reverse SOP Decompiler from Transcript History

## Bash execution contract

When calling `bash_code_execute_tool`, always pass **`reason`** (≥10 characters: why this command runs) and **`command`**. Put `reason` first.


## Overview

In enterprise operations, customer support, and IT incident triage, veteran operators execute complex decision-making through tacit knowledge. This knowledge rarely exists in written documentation—it is buried in thousands of hours of audio recordings, support chat tickets, and emergency Slack channels.

The **Reverse SOP Decompiler** acts as a process-mining intelligence layer that digests real-world dialogue transcripts, extracts implicit logic gates, and outputs:
1. **Auditable SOP Specification** (Markdown format).
2. **Visual Mermaid Decision Flowchart** (`graph TD`).
3. **Executable Agent Profile YAML** (Ready to mount onto a Myrmidon digital worker).

---

## 1. The Four-Stage Decompilation Pipeline

```text
Raw Dialogues / Call Transcripts ──> Noise Stripping & Intent Tagging
                                          │
                                          ▼
Causal Logic Mining ─────────────────────> 1. Trigger Conditions & Preconditions
                                          2. Branching Decision Gates (If/Else)
                                          3. Action Space (APIs, Tools, Queries)
                                          4. HITL Escalation Fallbacks
                                          │
                                          ▼
Dual Output Synthesis ───────────────────> 1. `docs/sop/{process_slug}.md` + Mermaid
                                          2. `agents/{process_slug}.yaml` Profile
```

---

## 2. Standard SOP Output Schema (`docs/sop/{process_slug}.md`)

Every decompiled SOP must adhere to this formal structure:

### 1. Process Metadata
- **Process ID & Name**: e.g., `SOP-FIN-042: 跨行退款异常与对账差异人工介入排障`
- **Trigger Event**: e.g., `系统收到退款挂起告警 (Webhook refund_pending) 且超过 2 小时未完成`
- **Execution Role**: `资深对账运维专员`

### 2. Mermaid Decision Flowchart
```mermaid
graph TD
    A[收到退款异常工单/告警] --> B{检查银行流水状态}
    B -->|流水已扣款但未出回执| C[调用 query_bank_settlement 查证]
    B -->|流水未扣款| D[调用 cancel_refund_order 取消挂起]
    C --> E{核验金额一致性}
    E -->|对账无误| F[调用 mark_refund_success 强制结算]
    E -->|金额或卡号不符| G[转接人工风控复核 HITL]
```

### 3. Step-by-Step Operational Matrix

| Step ID | Step Name | Condition / Precondition | Action & Tools | Expected Output | Fallback Escalation |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `STEP_01` | 渠道状态自检 | 工单创建后立即执行 | `api_check_channel(code)` | 渠道通畅或维护中 | 若维护中直接挂起工单 |
| `STEP_02` | 流水对齐比对 | 渠道状态正常 | `db_query_transactions` | 检索到 1 条账单记录 | 未查到记录转人工排查 |

---

## 3. Deployable Agent Profile Export (`agents/{process_slug}.yaml`)

To turn the decompiled SOP into an autonomous worker:

```yaml
id: sop-operator-{process_slug}
name: "{Process Name} Automation Agent"
description: "Decompiled digital worker implementing SOP-{slug} from transcript history."
system_prompt: >-
  You are an operations specialist strictly executing the procedures defined in SOP-{slug}.
  Always evaluate decision branches in the exact sequence specified by the Mermaid flowchart.
  Escalate to human review immediately if any transaction delta exceeds tolerance.
tools:
  - file_read_tool
  - bash_code_execute_tool
```
