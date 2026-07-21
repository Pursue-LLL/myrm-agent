---
name: code-review
description: >-
  Structured code review workflow following security → correctness → performance →
  maintainability priority order. Produces actionable feedback with severity levels.
version: 1.0.0
category: development
tags:
  - code-review
  - security
  - quality
  - best-practices
allowed-tools: file_read_tool grep_tool glob_tool bash_code_execute_tool
contract:
  steps:
    - "Phase 1: Context — understand the change scope, purpose, and affected systems"
    - "Phase 2: Security Review — check for vulnerabilities, injection, auth issues"
    - "Phase 3: Correctness Review — verify logic, edge cases, error handling"
    - "Phase 4: Performance Review — identify bottlenecks, unnecessary operations"
    - "Phase 5: Maintainability Review — naming, structure, documentation, test coverage"
  potential_traps:
    - description: "Reviewing style issues while missing security vulnerabilities"
      mitigation: "Follow strict priority order: security → correctness → performance → maintainability"
      severity: high
    - description: "Reviewing files in isolation without understanding the change context"
      mitigation: "Always read the full diff and understand the purpose before reviewing individual files"
      severity: medium
  verification_steps:
    - step_id: context_understood
      description: "Change purpose and scope are clearly understood"
      validation_method: "Can summarize what the change does and why in one paragraph"
      is_required: true
    - step_id: security_checked
      description: "No security vulnerabilities introduced"
      validation_method: "All input validation, auth checks, and data handling reviewed"
      is_required: true
  success_criteria: "All critical and high-severity issues identified with clear remediation guidance"
  estimated_duration_seconds: 1200
---

# Code Review


## Bash execution contract

When calling `bash_code_execute_tool`, always pass **`reason`** (≥10 characters: why this command runs) and **`command`**. Put `reason` first.

## Review Priority Order

```
SECURITY → CORRECTNESS → PERFORMANCE → MAINTAINABILITY
```

Never review style while security vulnerabilities exist. Fix critical issues first.

## Phase 1: Context

Before reviewing any code:

1. **Understand the purpose** — What problem does this change solve? What's the expected behavior?
2. **Identify the scope** — Which files changed? What systems are affected?
3. **Check for tests** — Are there new/updated tests? Do they cover the change?

**Action:** Use `file_read_tool` to read changed files. Use `grep_tool` to find related code.

## Phase 2: Security Review

Check for:

| Category | What to Look For |
|----------|-----------------|
| **Input Validation** | Unvalidated user input, missing sanitization, SQL injection vectors |
| **Authentication** | Missing auth checks, broken access control, privilege escalation |
| **Data Exposure** | Sensitive data in logs, responses, or error messages |
| **Injection** | Command injection, template injection, XSS vectors |
| **Dependencies** | Known vulnerable packages, unnecessary permissions |
| **Secrets** | Hardcoded credentials, API keys, tokens |

## Phase 3: Correctness Review

Check for:

- **Logic errors** — Off-by-one, incorrect conditions, missing cases
- **Edge cases** — Empty input, null values, boundary conditions, concurrent access
- **Error handling** — Are exceptions caught appropriately? Are errors propagated correctly?
- **State management** — Race conditions, stale data, inconsistent state transitions
- **Type safety** — Type mismatches, unsafe casts, missing validation

## Phase 4: Performance Review

Check for:

- **N+1 queries** — Database queries in loops
- **Unnecessary computation** — Repeated work, missing caching opportunities
- **Memory issues** — Unbounded collections, large object retention
- **I/O bottlenecks** — Synchronous I/O where async is appropriate
- **Algorithm complexity** — O(n²) where O(n log n) is possible

## Phase 5: Maintainability Review

Check for:

- **Naming clarity** — Do names convey intent? Are abbreviations clear?
- **Single responsibility** — Does each function/class do one thing?
- **DRY violations** — Is logic duplicated across files?
- **Documentation** — Are non-obvious decisions explained?
- **Test coverage** — Are critical paths tested? Are edge cases covered?

## Output Format

For each finding:

```
### [SEVERITY] Brief description

**File:** path/to/file.py:42
**Category:** Security / Correctness / Performance / Maintainability

**Issue:** Clear description of the problem.

**Impact:** What could go wrong if this isn't fixed.

**Suggestion:** Specific, actionable fix recommendation.
```

Severity levels:
- **CRITICAL** — Security vulnerability or data loss risk. Must fix before merge.
- **HIGH** — Correctness bug or significant performance issue. Should fix before merge.
- **MEDIUM** — Code quality issue that increases maintenance burden. Fix recommended.
- **LOW** — Style or minor improvement. Optional.
