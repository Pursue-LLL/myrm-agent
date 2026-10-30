# core/

## Overview
Agent Skills Evolution Core module.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package |   Init   | — |
| engine.py | Core | Skill evolution engine with 2 types (FIX/DERIVED) + EvalCase regression gate + Improvement Gate (baseline comparison for the DERIVED path). Both entry points work from the SKILL.md on disk (`skill_from_disk`), text and evolution lock, and check the lock after that overlay; the store is only read. | ✅ |
| skill_on_disk.py | Core | Disk source of the engine and the screener: `skill_from_disk` returns the skill with its content replaced by the SKILL.md text (`read_skill_md`) when that differs from the stored copy, ignoring line endings, and with `evolution_locked` set when the store's flag or the SKILL.md frontmatter lock is set (the frontmatter is read from the file even when its text is the same or larger than the store takes, and from the stored copy when the file cannot be read; a frontmatter the loaders reject does not lock). It returns the skill itself when neither the text nor the lock changes; the stored copy is never written. The editor, a version rollback and the agent's skill tool change the file but not the copy, a new skill carries its lock in the file only, and a proposal built from the copy would overwrite text the skill no longer has. | ✅ |
| eval_regression.py | Core | Baseline-relative EvalCase regression gate. Guards only the cases the original content passes (a case the original already fails — e.g. a Python AST check on a Markdown SOP — cannot regress), penalises each guarded case a variant drops and hard-filters a variant that drops all of them. | ✅ |
| proposal_builder.py | Core | Proposal Builder with edit_summary extraction, updated_eval_cases co-evolution sync, and integrated security scanning. Edit-summary JSON parsed via `parse_llm_json_object` (robust against fences, prose, trailing commas). Drops variants the skill loader would skip (`unloadable_reason`, which the evaluator reuses) and variants the security scan rejects, and records the scan summary of the rest. | ✅ |
| types.py | Config | Data types including EvolutionType (3 variants), EvolutionStrategy (balanced / innovate / repair-only), EvolutionLayer, FailurePathology, GeneCellKey, GeneEliteRecord, SkillRecord (with eval_cases), EvolutionProposal (with edit_summary, updated_eval_cases, security_scan_summary). | ✅ |
| gene_bank.py | Core | MAP-Elites Gene Bank Archive maintaining quality-diversity Pareto elites across 2D (Layer x Pathology) grid to prevent evolution collapse. | ✅ |
