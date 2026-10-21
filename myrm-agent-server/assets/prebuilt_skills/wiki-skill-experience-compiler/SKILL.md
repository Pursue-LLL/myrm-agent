---
name: wiki-skill-experience-compiler
description: >-
  Three-tier experience compiler and asymmetric self-evolution engine inspired by Google Research WikiSkill (arXiv:2608.27454).
  Decouples ephemeral execution traces, persistent concept Wiki articles, and executable Skill SOPs.
  Enforces the ironclad asymmetric principle: "Skill SOPs may be rolled back, but Wiki concept facts are NEVER rolled back."
version: 1.0.0
category: meta
tags:
  - wikiskill
  - experience-compiler
  - asymmetric-evolution
  - knowledge-base
  - self-learning
  - continuous-distillation
allowed-tools: file_read_tool file_write_tool file_edit_tool memory_save_tool memory_search_tool
contract:
  steps:
    - "Phase 1: Trace Ingestion & Fact Distillation — Extract domain entities, invariant ground truths, and environmental quirks from raw session logs"
    - "Phase 2: Persistent Wiki Article Crystallization — Compile extracted facts into evergreen `wiki/{domain}/{concept}.md` documents"
    - "Phase 3: Executable Skill SOP Compilation — Formulate high-level, procedural `SKILL.md` operating guides referencing compiled Wiki concepts"
    - "Phase 4: Asymmetric Versioning & Rollback Guard — Isolate Skill versions from Wiki knowledge; ensure rollback of procedural steps never deletes validated facts"
  potential_traps:
    - description: "Coupling factual knowledge directly into procedural SOP steps, losing domain knowledge when an SOP step is reverted"
      mitigation: "Strict 3-tier decoupling: raw trace -> persistent Wiki facts -> executable SOP reference pointers"
      severity: high
    - description: "Wiki concept article churn or duplicated entity creation across similar sessions"
      mitigation: "Run semantic entity deduplication against existing wiki markdown pages before creating a new entry"
      severity: medium
  verification_steps:
    - step_id: three_tier_separation_verified
      description: "Verify that operational procedure references Wiki concepts rather than inlining volatile factual data"
      validation_method: "Inspect generated SKILL.md for wiki/ links or concept references"
      is_required: true
    - step_id: asymmetric_rollback_inviolable
      description: "Ensure contract declares zero-deletion rule for validated Wiki facts upon Skill rollback"
      validation_method: "Check phase 4 contract instructions for explicit rollback isolation"
      is_required: true
  success_criteria: "A robust 3-tier knowledge compilation pipeline where operational skills evolve safely while enterprise domain facts permanently accumulate."
  estimated_duration_seconds: 240
---

# WikiSkill Three-Tier Experience Compiler & Asymmetric Evolution

You are an elite Knowledge Engineering Architect and Self-Evolving Systems Specialist implementing the **WikiSkill Three-Tier Architecture** (Google Research, arXiv:2608.27454v1).

Traditional self-evolving agents directly modify their prompts or SOPs after encountering failure or success. When an updated prompt degrades performance in edge cases, rolling back the prompt discards all discovered domain facts, causing "amnesic regression."

`wiki-skill-experience-compiler` enforces a **3-tier decoupled memory hierarchy** with **asymmetric evolution**.

---

## 1. The Three-Tier Architecture

```
Layer 1: Raw Ephemeral Execution Traces (会话运行时轨迹)
         - Tool calls, shell exit codes, stdout/stderr, API payloads.
         - Short-lived, voluminous, noisy.
                        │
                        ▼ (Distillation & Grounding)
Layer 2: Persistent Concept Wiki Articles (永久概念维基事实库)
         - File path: `wiki/{domain}/{concept_name}.md`
         - Objective ground truths, environment quirks, entity relationship specs.
         - **NON-PROCEDURAL, FACTUAL, CUMULATIVE**.
                        │
                        ▼ (Compilation & Proceduralization)
Layer 3: Executable Skill SOPs (可执行操作规约)
         - File path: `assets/prebuilt_skills/{name}/SKILL.md`
         - Step-by-step algorithms, tool selection, priority heuristics.
         - **PROCEDURAL, LEAN, VERSION-CONTROLLED, ROLLBACK-PERMISSIVE**.
```

---

## 2. The Asymmetric Evolution Invariant

> **"Skill SOPs may be rolled back, but Wiki concept facts are NEVER rolled back."**
> *(Skill 回滚，但 Wiki 永不回滚)*

- When an updated Skill SOP causes a regression, revert the `SKILL.md` commit to the prior known-good version.
- **DO NOT** delete or revert the `wiki/` markdown articles created or expanded during the incident. The environment quirk, API rate limit, or domain entity discovered during that incident remains objectively true.
- Subsequent iterations of the Skill will compile against the updated, richer Wiki layer, preventing the agent from repeating the same discovery trial.

---

## 3. Four-Phase Compilation SOP

### Phase 1: Fact Distillation
Extract domain invariants from session traces:
- API endpoint behaviors, rate limits, undocumented header requirements.
- File schema quirks, encoding traps, proprietary business rules.

### Phase 2: Wiki Crystallization
Write or patch `wiki/{domain}/{concept}.md`:
```markdown
# [Concept]: {Concept Name}
- **Category**: Entity / Environment Quirk / Business Constraint
- **Verified On**: YYYY-MM-DD
- **Ground Truth**: {Clear, concise factual description}
- **Observed Constraints**: {Specific limits, parameters, or caveats}
```

### Phase 3: Skill Compilation
Update `SKILL.md` to reference the canonical Wiki concept:
- In `Phase 1: Verify`, add: *"Consult `wiki/{domain}/{concept}.md` for verified environment constraints."*

### Phase 4: Asymmetric Safety Audit
Tag Git commits distinctly:
- `feat(wiki): add {concept} domain ground truth`
- `fix(skill): adapt {skill_name} procedure to respect {concept}`
When rolling back, only revert `fix(skill)`, keeping `feat(wiki)`.
