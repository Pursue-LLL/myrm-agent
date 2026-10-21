---
name: wiki-skill-three-tier
description: >-
  Three-tier experience compilation and asymmetric self-evolution engine based on Google
  Research WikiSkill (arXiv:2608.27454v1). Decouples continuous agent learning into three
  distinct layers: Raw Traces (ephemeral runtime history) -> Persistent Wiki Knowledge
  (permanent concepts & verified facts) -> Actionable Skill SOPs (executable protocols).
  Enforces the asymmetric rule: Skill SOPs can be rolled back upon regression, but Wiki
  knowledge is permanent and never rolled back.
version: 1.0.0
category: meta-learning
tags:
  - wikiskill
  - three-tier-architecture
  - asymmetric-evolution
  - self-evolving-agent
  - knowledge-compilation
  - skill-synthesis
  - 三层解耦
  - 非对称演化
  - 知识沉淀
allowed-tools: wiki_ingest_tool wiki_query_tool wiki_apply_tool file_read_tool file_write_tool
contract:
  steps:
    - "Phase 1: Raw Trace Distillation — ingest multi-turn execution trajectory, filtering noise to extract verified domain discoveries and edge-case exceptions"
    - "Phase 2: Tier 2 Wiki Compilation — crystallize domain discoveries into permanent LLM Wiki concepts/facts with bidirectional wikilinks (`concepts/{domain}/{slug}.md`)"
    - "Phase 3: Tier 3 Skill SOP Synthesis — compile refined operational rules and negative guardrails into executable `SKILL.md` SOP contracts"
    - "Phase 4: Asymmetric Regression Defense — if a new skill version regresses on benchmark tests, roll back the Skill SOP to v0 while keeping Tier 2 Wiki knowledge permanently intact"
  potential_traps:
    - description: "Rolling back verified domain facts when an action SOP fails testing"
      mitigation: "Strict Asymmetric Invariant: Wiki knowledge repository is strictly append/update and immune to Skill SOP version rollbacks"
      severity: high
    - description: "Overfitting Skill SOPs with one-off episodic noise instead of crystallized knowledge"
      mitigation: "Require all skill modifications to cite specific verified Wiki concept paths as prerequisite rationale"
      severity: high
  verification_steps:
    - step_id: wiki_concept_crystallized
      description: "Ensure new domain insights are persisted in LLM Wiki before touching Skill SOP"
      validation_method: "Verify concept file created via `wiki_apply` or present in `concepts/`"
      is_required: true
    - step_id: skill_sop_updated_with_citation
      description: "Ensure updated SKILL.md explicitly cites the underlying Wiki concepts"
      validation_method: "Check presence of `[[Wiki Concept]]` links in SOP rationale"
      is_required: true
  success_criteria: "A verified three-tier evolution cycle where raw experience compounds into permanent Wiki facts and drives resilient, rollback-safe Skill SOPs"
  estimated_duration_seconds: 400
---

# WikiSkill Three-Tier Experience Compilation & Asymmetric Evolution

## Overview

Traditional agent self-evolution conflates **factual domain knowledge** with **action protocols**. When an updated skill performs poorly and is rolled back, the valuable facts learned during the run are lost. Conversely, polluting operational prompts with raw session noise causes prompt bloat and performance drift.

The `wiki-skill-three-tier` engine implements Google Research's **WikiSkill (arXiv:2608.27454v1)** three-tier decoupled architecture:

```
┌────────────────────────────────────────────────────────┐
│             WikiSkill Three-Tier Architecture          │
├───────────────────┬───────────────────┬────────────────┤
│  Tier 1: Traces   │   Tier 2: Wiki    │ Tier 3: Skills │
│ (Ephemeral Memory)│(Permanent Truths) │(Executable SOP)│
├───────────────────┼───────────────────┼────────────────┤
│ • Raw tool outputs│ • Verified facts  │ • Steps & Traps│
│ • User queries    │ • Domain concepts │ • Tool bindings│
│ • Error traces    │ • Bidirectional   │ • Versioned    │
│ • TTL: Ephemeral  │ • NEVER rollback  │ • Rollback-safe│
└───────────────────┴───────────────────┴────────────────┘
```

## The Asymmetric Evolution Invariant

$$\text{Rollback}(\text{Skill}_{v+1} \to \text{Skill}_v) \implies \text{Wiki Knowledge is PRESERVED}$$

1. **Tier 1 (Raw Traces)**: Short-term logs, scratchpads, and dialogue turns.
2. **Tier 2 (Persistent LLM Wiki)**: Distilled facts, API quirks, data schemas, and domain invariants stored in `concepts/`. This layer is **permanent, compounding, and never deleted upon skill regression**.
3. **Tier 3 (Actionable Skill SOPs)**: The high-level rules, instructions, and tool declarations in `SKILL.md`. This layer is strictly versioned and can be rolled back instantly if benchmark accuracy drops.

## The 4-Phase Compilation Cycle

1. **Trace Distillation**: Parse execution traces to isolate novel facts (e.g. "PostgreSQL 16 requires `scram-sha-256` authentication").
2. **Wiki Crystallization**: Invoke `wiki_apply` to record the invariant into `concepts/infrastructure/postgres_auth.md`.
3. **SOP Update**: Update the database diagnostic skill's `potential_traps` with a citation: `See [[PostgreSQL Auth]]`.
4. **Benchmark Verification**: If the updated skill passes evaluation, commit the version; if it fails, revert `SKILL.md` to previous commit while retaining the Wiki concept.

## Standard Execution SOP

1. **Extract Discovery**: Read completed session logs to identify durable facts vs temporary noise.
2. **Persist to Wiki**: Commit structured concept via `wiki_apply` with tags and wikilinks.
3. **Refine Skill SOP**: Formulate concise rule update referencing the new Wiki concept.
4. **Assert Invariance**: Confirm that a simulated skill rollback leaves the Wiki concept completely intact.
