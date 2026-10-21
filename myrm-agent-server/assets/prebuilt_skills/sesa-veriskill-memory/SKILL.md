---
name: sesa-veriskill-memory
description: >-
  Enterprise-grade skill for evolving skill memory and executable attribution verification,
  implementing the SESA (Self-Evolving Skill Agent, arXiv:2607.29468) and VeriSkill (arXiv:2607.27733) frameworks.
  Performs 4-way causal failure attribution (Prompt, Tool, Knowledge, Environment), Help-Hurt net-score pruning,
  and mandatory benchmark execution verification gates before promoting mutated skills to production.
version: 1.0.0
category: meta-engineering
tags:
  - sesa
  - veriskill
  - skill-memory
  - attribution-gate
  - causal-attribution
  - benchmark-verification
  - 技能进化
  - 归因门禁
  - 净分淘汰
allowed-tools: file_read_tool file_write_tool file_edit_tool bash_code_execute_tool
contract:
  steps:
    - "Phase 1: Trace Ingestion & 4-Way Causal Attribution — Classify execution failure into Prompt Defect, Tool Misuse, Missing Knowledge, or Environmental Transient"
    - "Phase 2: Evolving Skill Memory Distillation — Extract atomic corrective rules and update skill memory bank with provenance tracking"
    - "Phase 3: Help-Hurt Net-Score Calculation — Compute ΔScore = Success_gain - Regression_penalty across historical benchmark suites"
    - "Phase 4: Executable Attribution Verification Gate — Execute deterministic test harness; strictly reject mutations that fail regression checks"
  potential_traps:
    - description: "Attributing infrastructure network timeouts to prompt logic, causing unnecessary prompt churn"
      mitigation: "Strict Environmental Transient filter: network/5xx HTTP errors are quarantined and excluded from prompt mutation"
      severity: critical
    - description: "Promoting a skill mutation that fixes one test case but silently breaks three others (Negative Transfer)"
      mitigation: "Mandatory Help-Hurt Net Score verification: reject any mutation where Net Score <= 0"
      severity: critical
    - description: "Unbounded memory bloat leading to context window exhaustion"
      mitigation: "Prune low-utility memory entries with Help Count == 0 after 10 benchmark cycles"
      severity: medium
  verification_steps:
    - step_id: attribution_matrix_complete
      description: "Ensure causal attribution report categorizes errors into exact SESA 4-way buckets"
      validation_method: "Inspect attribution breakdown table in output artifact"
      is_required: true
    - step_id: net_score_gate_enforced
      description: "Verify that Net-Score (Help - Hurt) is strictly positive before skill promotion"
      validation_method: "Assert net_score > 0 from benchmark evaluation"
      is_required: true
  success_criteria: "An anti-fragile skill evolution pipeline where only mathematically proven, regression-free skill patches are committed."
  estimated_duration_seconds: 400
---

# SESA & VeriSkill: Evolving Skill Memory & Executable Attribution Gate

## Bash execution contract

When calling `bash_code_execute_tool`, always pass **`reason`** (≥10 characters: why this command runs) and **`command`**. Put `reason` first.


You are a Principal **Autonomous Agent Safety & Evaluation Architect** implementing the state-of-the-art **SESA (Self-Evolving Skill Agent, arXiv:2607.29468)** and **VeriSkill (arXiv:2607.27733)** frameworks.

Self-evolving agents often fall into the trap of **"Pseudoscience Mutation"**: blindly rewording prompts based on a single failed execution, inadvertently introducing regressions to previously working features (Negative Transfer).

This skill provides an audit-grade, mathematically grounded pipeline for **4-Way Causal Attribution**, **Help-Hurt Net-Score Pruning**, and **Deterministic Benchmark Verification**.

---

## 1. The 4-Way Causal Attribution Matrix (四分类责任因果归因雷达)

When an agent execution fails or produces sub-optimal results, do NOT immediately mutate the skill prompt. First, attribute the root cause into one of four orthogonal buckets:

| Failure Category | Concrete Diagnostic Evidence | Corrective Action | Skill Prompt Mutation? |
| :--- | :--- | :--- | :--- |
| **1. Environmental Transient (环境瞬时抖动)** | Network connection drop, 502/503/504 HTTP status, rate limits (429), disk full | Log retry telemetry; do NOT touch skill prompt | ❌ FORBIDDEN |
| **2. Tool Interface Defect (工具契约缺陷)** | Tool schema mismatch, missing required argument, crash inside Python executor | Patch tool code or update schema definitions | ❌ NO (Tool Layer) |
| **3. Missing Domain Knowledge (领域知识缺失)** | Agent followed rules correctly but lacked proprietary business context | Ingest facts into `llm_wiki` or Long-Term Memory | ❌ NO (Knowledge Layer) |
| **4. Skill SOP Flaw (技能规范逻辑缺陷)** | Ambiguous instructions, flawed reasoning step, missing negative constraint | Extract atomic corrective rule into Skill Memory Bank | ✅ PERMITTED |

---

## 2. Help-Hurt Net-Score Pruning Protocol (Help-Hurt 净分淘汰法则)

Every proposed mutation to a skill's SOP must undergo rigorous regression evaluation against a historical validation set $D_{val}$:

$$\Delta \text{Net-Score} = N_{\text{helped}} - 2 \times N_{\text{hurt}}$$

- $N_{\text{helped}}$: Number of previously failing test cases now passing with the mutated skill.
- $N_{\text{hurt}}$: Number of previously passing test cases that now regress/fail.
- **The Asymmetric Penalty**: Hurting existing capabilities is penalized at **double weight** ($2\times$) to prevent capability erosion.
- **Promotion Threshold**: A skill mutation is **ONLY** approved for production if $\Delta \text{Net-Score} > 0$. If $\le 0$, the mutation is immediately quarantined and discarded.

---

## 3. Four-Phase Verification Gate SOP

### Phase 1: Failure Log Ingestion
- Parse multi-turn execution trace and isolated failure step.
- Classify against the 4-Way Causal Attribution Matrix. If non-SOP category, exit gracefully and redirect to responsible system layer.

### Phase 2: Memory Synthesis & Atomic Rule Extraction
- Formulate a single, concise corrective constraint:
  `"When encountering context [C], NEVER do [A]; instead, perform [B] because of [Reason]."`
- Record trace provenance ID.

### Phase 3: Benchmark Suite Execution
- Run automated test runner via `bash_code_execute_tool` across the skill's regression suite.
- Measure execution pass rate, token consumption delta, and latency delta.

### Phase 4: Net-Score Verification & Promotion
- If $\Delta \text{Net-Score} > 0$: Merge patch into `SKILL.md` (or workspace skill), increment patch version, and record to skill memory ledger.
- If $\Delta \text{Net-Score} \le 0$: Log rejection to `evolution_rejections.jsonl` with failure trace and preserve baseline.
