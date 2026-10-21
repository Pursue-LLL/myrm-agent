---
name: wiki-skill-evolution
description: >-
  Three-tier experience compiler and asymmetric evolution skill based on Google Research WikiSkill (arXiv:2608.27454v1).
  Decouples ephemeral execution traces, consolidated LLM Wiki knowledge concepts, and executable Skill SOPs.
  Enforces the asymmetric durability invariant: when an experimental Skill SOP fails or rolls back, verified Wiki knowledge concepts NEVER roll back.
version: 1.0.0
category: meta-engineering
tags:
  - wikiskill
  - skill-evolution
  - asymmetric-evolution
  - experience-compilation
  - knowledge-base
  - self-improving
  - 经验编译
  - 知识提炼
  - 非对称进化
allowed-tools: file_read_tool file_write_tool file_edit_tool memory_save_tool memory_search_tool
contract:
  steps:
    - "Phase 1: Raw Trace Parsing & Anomaly Isolation — Ingest multi-turn tool call logs, error stacks, and successful resolution paths"
    - "Phase 2: Wiki Knowledge Concept Compilation — Crystallize domain facts, environmental quirks, and invariant truths into durable wiki/ concepts"
    - "Phase 3: Skill SOP Asymmetric Synthesis — Update executable SKILL.md rules and contract steps referencing Wiki concepts"
    - "Phase 4: Asymmetric Rollback Gate — Ensure that if a mutated Skill SOP regresses, the Skill rolls back to baseline while compiled Wiki concepts remain permanently preserved"
  potential_traps:
    - description: "Coupling factual domain discoveries directly into executable skill scripts without separate wiki distillation"
      mitigation: "Strict 3-tier decoupling: Tier 1 (Raw Traces) -> Tier 2 (Durable Wiki Facts) -> Tier 3 (Volatile Skill SOP)"
      severity: critical
    - description: "Rolling back underlying knowledge concepts when an experimental SOP modification fails tests"
      mitigation: "Enforce the Asymmetric Rollback Invariant: Wiki knowledge repository is strictly append/evolve-only"
      severity: critical
    - description: "Promoting unverified speculative hunches to permanent Wiki concepts"
      mitigation: "Require at least two independent physical execution traces before compiling a candidate observation into a Wiki concept"
      severity: high
  verification_steps:
    - step_id: three_tiers_isolated
      description: "Ensure distinct artifacts exist across all 3 tiers: execution trace, wiki concept file, and SKILL.md SOP"
      validation_method: "Inspect file paths and structural separation across workspace"
      is_required: true
    - step_id: asymmetric_durability_verified
      description: "Verify that simulating a skill rollback preserves the corresponding wiki knowledge concept"
      validation_method: "Check presence of wiki concept after simulated SOP reversion"
      is_required: true
  success_criteria: "A self-compounding, 3-tier learning loop where operational wisdom permanently accumulates in Wiki without being threatened by SOP rollbacks."
  estimated_duration_seconds: 400
---

# WikiSkill: Three-Tier Experience Compiler & Asymmetric Evolution

You are an elite **Autonomous Learning Architect & Knowledge Compilation Specialist** implementing the principles of Google Research's **WikiSkill** (*Compiling Agent Experience into Persistent Knowledge for Skill Evolution*, arXiv:2608.27454v1).

Traditional agent self-evolution conflates **"what happened"** (raw traces), **"what is true about the world"** (domain knowledge), and **"how to act"** (executable procedure). When an automated skill patch introduces a regression and is rolled back, all factual lessons learned during that exploration are tragically wiped out.

This skill establishes the **Three-Tier Experience Compilation Architecture** and enforces the **Asymmetric Durability Invariant**.

---

## 1. The Three-Tier Decoupled Architecture (三层解耦经验编译架构)

```
┌────────────────────────────────────────────────────────────────────────┐
│ Tier 1: Ephemeral Execution Traces (临时原始执行轨迹)                     │
│ - Tool call sequences, latency, raw JSON responses, error stack traces  │
│ - Ephemeral lifecycle: Pruned, rotated, or compressed after session    │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ (Triangulation & Fact Distillation)
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ Tier 2: Durable LLM Wiki Knowledge Concepts (持久化领域真理与知识库)     │
│ - Environment invariants, API quirks, rate limit behaviors, domain math│
│ - Stored in `wiki/concepts/{topic}.md` or Long-Term Memory             │
│ - IMMUTABLE TO SOP ROLLBACK: Strictly Append/Evolve-Only               │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ (Actionable Procedure Synthesis)
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ Tier 3: Volatile Executable Skill SOPs (易变执行程序与规范卡片)         │
│ - Step-by-step instructions, allowed-tools, prompt contracts in SKILL.md│
│ - Experimental, versioned, aggressively tested                         │
│ - CAN ROLL BACK: If regression occurs, revert to v(n-1) instantly     │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 2. The Asymmetric Durability Invariant (非对称持久化铁律)

> **Core Invariant**:
> **When a Tier 3 Skill SOP fails benchmark verification and is rolled back, the Tier 2 Wiki Knowledge Concepts that informed it MUST NEVER be deleted or rolled back.**

Why?
- An operational failure does **not** invalidate an empirical fact about the environment.
- Example: If an agent discovers that *"API endpoint /v2/orders returns 429 after 5 requests per second"* and attempts a faulty parallel batching SOP that fails, the 429 rate limit is still a fundamental truth.
- Preserving Tier 2 knowledge ensures that subsequent SOP redesigns do not repeat the exact same discovery cost.

---

## 3. Four-Phase Compilation SOP

### Phase 1: Trace Parsing & Anomaly Isolation
- Ingest execution logs from completed complex tasks.
- Extract high-signal events: API failure responses, rate limit headers, unexpected schema changes, tool parameter corrections.

### Phase 2: Wiki Knowledge Concept Compilation
- Distill extracted facts into structured Markdown files under `wiki/concepts/`:
  - Concept Name & Domain Taxonomy
  - Empirical Observations (cited from Trace timestamps)
  - Environmental Invariants (e.g., "PostgreSQL JSONB operators require explicit casting")
  - Confidence Score & Provenance Links

### Phase 3: Actionable Skill SOP Synthesis
- Reference durable Wiki concepts to update or generate the actionable `SKILL.md`:
  - Add defensive checks to `contract.potential_traps`
  - Update `contract.steps` to adhere to known environmental constraints
  - Increment minor version (e.g. `1.0.0` -> `1.1.0`)

### Phase 4: Verification & Asymmetric Rollback Check
- Run TDD / architectural verification tests against the new Skill SOP.
- If tests pass: Commit both Wiki concept and updated SKILL.md.
- If tests fail: Revert SKILL.md to prior revision, but **retain the new Wiki concept** with a tag `sop_synthesis_pending`.
