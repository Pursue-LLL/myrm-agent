---
name: lean-coding
description: >-
  Anti-bloat coding discipline with a 7-rung necessity ladder. Prevents AI
  over-engineering by forcing a check at each rung before writing new code:
  YAGNI → reuse existing → stdlib → platform native → installed dep → one-liner
  → minimum code. Includes root-cause bug fix protocol and over-engineering
  detection tags. Bind to any coding-oriented agent for cleaner output and
  lower token cost.
version: 1.0.0
category: development
tags:
  - lean-coding
  - yagni
  - anti-bloat
  - code-quality
  - minimal
  - efficiency
allowed-tools: file_read_tool grep_tool glob_tool bash_code_execute_tool
contract:
  steps:
    - "Phase 1: Understand — read the task and trace affected code end to end"
    - "Phase 2: Climb the Ladder — stop at the first rung that solves the problem"
    - "Phase 3: Implement — write the minimum code that works, if ladder demands it"
    - "Phase 4: Validate — verify the solution, check for regressions"
  potential_traps:
    - description: "Skipping the ladder and jumping straight to writing new code"
      mitigation: "Always start from rung 1; record which rung held"
      severity: high
    - description: "Re-implementing a utility that already exists in the codebase"
      mitigation: "Use grep/glob to search the codebase before writing anything new"
      severity: high
    - description: "Adding a new dependency when stdlib or an installed package covers it"
      mitigation: "Check stdlib and installed packages before adding any new dependency"
      severity: medium
  verification_steps:
    - step_id: ladder_applied
      description: "The necessity ladder was applied; the chosen rung is stated"
      validation_method: "Response mentions which rung held and why higher rungs did not"
      is_required: true
    - step_id: no_unrequested_abstractions
      description: "No interfaces, factories, or layers were added unless explicitly requested"
      validation_method: "Code review confirms zero unrequested abstractions"
      is_required: true
  success_criteria: "Problem solved at the highest possible rung with the smallest working diff"
  estimated_duration_seconds: 900
---

# Lean Coding

## The Necessity Ladder

Before writing any code, climb this ladder. Stop at the first rung that holds:

| Rung | Check | Action |
|------|-------|--------|
| 1 | Does this need to exist at all? | Skip it. Say why in one line. (YAGNI) |
| 2 | Does it already exist in this codebase? | Reuse. Search with `grep` / `glob` / `ast_search` before writing. |
| 3 | Does the standard library do this? | Use it. No wrapper. |
| 4 | Does a native platform feature cover it? | Use it. CSS over JS, DB constraint over app code, `<input type="date">` over a picker lib. |
| 5 | Does an already-installed dependency solve it? | Use it. Never add a new dep for what a few lines can do. |
| 6 | Can this be one line? | Write one line. |
| 7 | Only then: | Write the minimum code that works. |

The ladder runs **after** you understand the problem — read the task, trace the code it touches, then climb. Two rungs work → take the higher one.

## Bug Fix Protocol

A bug report names a **symptom**. Before editing:

1. Grep every caller of the function you are about to touch
2. Fix the **shared root cause once** — one guard in the shared function is a smaller diff than one per caller
3. Patching only the reported path leaves sibling callers still broken

## Over-Engineering Detection

When reviewing code (yours or existing), tag issues:

| Tag | Meaning | Action |
|-----|---------|--------|
| `delete` | Dead code, unused flexibility, speculative feature | Remove it |
| `stdlib` | Hand-rolled thing the standard library ships | Replace with stdlib call |
| `native` | Dependency doing what the platform already does | Replace with native feature |
| `yagni` | Abstraction with one implementation, config nobody sets | Inline it |
| `shrink` | Same logic, fewer lines possible | Rewrite shorter |

## Rules

- No unrequested abstractions: no interface with one implementation, no factory for one product, no config for a value that never changes
- No boilerplate or scaffolding "for later"
- Deletion over addition; boring over clever
- Fewest files possible; shortest working diff wins
- Two stdlib options, same size? Pick the edge-case-correct one
- Complex request? Ship the lean version and note: "Did X; need full Y? Say so."

## Output

Code first. Then at most three short lines: what was skipped, when to add it. No essays.

Pattern: `[code] → Rung N held. Skipped: [X], add when [Y].`

## When NOT to Be Lean

Never simplify away:

- Input validation at trust boundaries
- Error handling that prevents data loss
- Security measures
- Accessibility basics
- Anything explicitly requested
- Non-trivial logic must leave ONE runnable check (assert-based self-check or one small test)
