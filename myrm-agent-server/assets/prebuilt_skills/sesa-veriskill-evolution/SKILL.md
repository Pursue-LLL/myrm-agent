---
name: sesa-veriskill-evolution
description: >-
  Self-evolving skill memory and executable attribution gate engine based on SESA (arXiv:2607.29468)
  and VeriSkill (arXiv:2607.27733). Filters skill modifications through a 4-way attribution model
  (Agent Planning, Tool/Env Flaw, Prompt Ambiguity vs Skill Defect), evaluates candidates across
  a shadow regression test benchmark, and enforces a strict Help-Hurt net scoring gate before admission.
version: 1.0.0
category: ai-evolution
tags:
  - sesa
  - veriskill
  - skill-evolution
  - attribution-gate
  - help-hurt-scoring
  - regression-benchmark
  - anti-degradation
  - 技能自演化
  - 责任归因门禁
  - 净分淘汰
license: MIT
allowed-tools: file_read_tool file_write_tool bash_code_execute_tool
contract:
  steps:
    - 1. Ingest task failure trace and run 4-way attribution classifier to isolate true skill instruction defects
    - 2. If attribution confirms skill defect, draft localized candidate rule patch with minimal semantic perturbation
    - 3. Replay candidate patch against historical golden test benchmark in an isolated shadow sandbox
    - 4. Calculate Net Help-Hurt score: Delta = Help_Count - Hurt_Count across the benchmark
    - 5. Admit candidate patch into authoritative skill asset only if Delta > 0 and regression rate is 0%
  potential_traps:
    - Overfitting on transient external environment failures (e.g. HTTP 429/500) and corrupting stable skills
    - Merging candidate patches that resolve a single edge case but break existing standard workflows
    - Allowing self-evolution to bloat skill prompts beyond context efficiency limits
    - Silently mutating skill files without keeping versioned diff logs and rollback snapshots
  verification_steps:
    - Verify 4-way attribution log exists and explicitly rules out environmental/user prompt issues
    - Confirm Help-Hurt benchmark score produces Delta > 0 with zero broken regression cases
    - Validate updated SKILL.md parses cleanly and adheres to schema specifications
  success_criteria:
    - Continuous monotonic improvement in agent skill success rate without catastrophic degradation
    - 100% rejection of spurious modifications triggered by external environment anomalies
---

# SESA & VeriSkill: Evolving Skill Memory & Attribution Gate Engine

## Bash execution contract

When calling `bash_code_execute_tool`, always pass **`reason`** (≥10 characters: why this command runs) and **`command`**. Put `reason` first.


When AI Agents are equipped with self-evolution capabilities, they often suffer from **catastrophic degradation**:
a transient external API outage or ambiguous user prompt causes the agent to mistakenly "fix" an already working skill,
corrupting previously reliable workflows.

Inspired by joint research from Peking University, Tsinghua, CAS, and USTC (**SESA**, arXiv:2607.29468) and
Peking University's **VeriSkill** (arXiv:2607.27733), this skill establishes an **Executable Attribution Gate &
Help-Hurt Net Scoring Admission Engine**.

---

## 1. The 4-Way Attribution Gate (四分类责任归因)

Before any skill modification is allowed, the failure trace MUST be classified into one of 4 buckets:

```
                          ┌───────────────────────────┐
                          │     Task Failure Trace    │
                          └─────────────┬─────────────┘
                                        ▼
                     ┌──────────────────────────────────────┐
                     │    4-Way Attribution Filter (SESA)   │
                     └──────────────────┬───────────────────┘
                                        │
      ┌──────────────────┬──────────────┴─────┬──────────────────┐
      ▼                  ▼                    ▼                  ▼
[1. User Ambiguity] [2. Env Flaw / 429] [3. Planner Drift] [4. Skill Defect]
      │                  │                    │                  │
   (REJECT)           (REJECT)             (REJECT)           (PROCEED)
```

1. **User Prompt Ambiguity**: User omitted crucial constraints. -> *Do NOT modify skill; prompt user for clarification.*
2. **Environment / Tool Flaw**: Network timeout, API rate limit, filesystem permission error. -> *Do NOT modify skill.*
3. **Agent Planner Drift**: Model failed to follow clear skill instructions despite valid SOP. -> *Do NOT modify skill.*
4. **Skill Instruction Defect**: The SOP was incomplete, contained misleading tool signatures, or lacked edge-case guidance. -> **Proceed to Candidate Generation.**

---

## 2. Help-Hurt Net Scoring Formula (VeriSkill 准入门禁)

For any candidate patch $P$, evaluate it against the golden evaluation benchmark $\mathcal{D}_{test}$:

$$\Delta(P) = \sum_{x \in \mathcal{D}_{test}} \mathbb{I}[\text{Success}(P, x) \land \neg \text{Success}(P_0, x)] - \sum_{x \in \mathcal{D}_{test}} \mathbb{I}[\neg \text{Success}(P, x) \land \text{Success}(P_0, x)]$$

$$\Delta(P) = \text{Help Count} - \text{Hurt Count}$$

### Admission Rule
- If $\text{Hurt Count} > 0$: **IMMEDIATE REJECTION** (Zero-regression policy).
- If $\Delta(P) \le 0$: **REJECTION** (No net gain).
- If $\text{Hurt Count} == 0$ and $\Delta(P) > 0$: **ADMIT & COMMIT**.
