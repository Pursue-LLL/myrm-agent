---
name: test-audit
description: >-
  Audit the quality of an existing test suite. Actually runs the tests, captures
  coverage evidence, then adversarially analyzes gaps, weak assertions, and
  anti-patterns. Produces a prioritized report only — it never writes tests.
version: 1.0.0
category: development
tags:
  - testing
  - quality
  - coverage
  - audit
  - maintenance
allowed-tools: file_read_tool grep_tool glob_tool bash_code_execute_tool
contract:
  steps:
    - "Phase 1: Discover — locate test files and load the project's testing conventions"
    - "Phase 2: Verify — actually run the suite and capture real coverage evidence"
    - "Phase 3: Audit — analyze gaps, assertion strength, and anti-patterns, then produce a prioritized report"
  potential_traps:
    - description: "Judging test quality from reading code without running the suite"
      mitigation: "Always run the tests and base every finding on real pass/fail and coverage output"
      severity: high
    - description: "Equating a high coverage percentage with good tests"
      mitigation: "Coverage is a hint, not a goal. Prioritize assertion strength and meaningful scenarios over percentages"
      severity: high
  verification_steps:
    - step_id: suite_ran
      description: "The test suite was executed and results captured"
      validation_method: "Report contains real pass/fail counts from the actual test run"
      is_required: true
    - step_id: report_prioritized
      description: "Findings are ordered by severity"
      validation_method: "Report uses P0/P1/P2 severity labels"
      is_required: true
  success_criteria: "A prioritized gap report where every finding is backed by concrete evidence from the test run"
  estimated_duration_seconds: 1800
---

# Test Audit

You audit the quality of an existing test suite. You do **not** write tests unless the user explicitly approves after seeing the report.

## Bash execution contract

When calling `bash_code_execute_tool`, always pass **`reason`** (≥10 characters: why this command runs) and **`command`**. Put `reason` first.

## Report First, Fix Later

Your deliverable is a report, not changes.

1. Complete all three phases and deliver the full report.
2. Writing or modifying tests is a separate step, handled by the main agent using `test-driven-development` discipline after the report is approved. This skill audits; it does not write.

## Phase 1: Discover

1. Find test files: `glob_tool` for `**/test_*.py`, `**/*.test.ts`, `**/*.spec.ts`, or the project's test convention.
2. Identify the framework and how tests are run:
   - Python: `pytest`
   - TypeScript/JavaScript: `vitest`, `jest`
   - Others: match the project's existing setup
3. Load the testing conventions:
   - Read the test config (`pyproject.toml`, `pytest.ini`, `vitest.config.*`, `jest.config.*`)
   - Note configured coverage tools and thresholds
4. Note which areas of the codebase appear untested — this becomes the audit checklist.
5. If no test files exist at all, stop: report a P0 finding (a project with zero tests has the largest possible coverage gap) and ask whether the user wants to start with `test-driven-development`.

**Action:** Use `glob_tool` to find tests. Use `file_read_tool` to read config files.

## Phase 2: Verify — Actually Run the Tests

Run the suite and capture real evidence. Never skip this phase.

```bash
pytest tests/ -q
# or, with coverage:
pytest tests/ --cov=<package> --cov-report=term
```

For TypeScript/JavaScript:

```bash
vitest run
# or:
vitest run --coverage
```

Guidelines:

- Run the full suite first; then run coverage for the target area if the full run is slow.
- Capture: pass count, fail count, skipped count, and coverage percentage per module.
- If the suite fails, list the failures — a suite that doesn't pass cannot be trusted, and this is a P0 finding by itself.
- If coverage is unavailable (no tool installed, or the coverage provider is missing), run the suite without coverage and state clearly in the report that coverage could not be measured — never fabricate numbers.
- If no coverage tool is configured, run with one; note the tool and its measuring scope in the report so numbers are comparable.

## Phase 3: Audit

Analyze the evidence and the test code. Look for:

### Coverage gaps

- Critical modules, error paths, and boundary conditions with no tests at all
- Functions whose branches are untested — not just missing line coverage, but missing scenarios
- Integration points (I/O, network, database) that are skipped entirely

### Weak assertions

- Tests that only check the call succeeded (`result is not None`) but not the actual behavior
- Tests asserting against implementation details instead of public behavior
- Tests that would pass even if the code under test were deleted (assertion vacuously true)
- Error-path tests that don't assert the error message or type

### Anti-patterns

- Duplicated test logic that could mask the duplication in the code under test
- Tests sharing mutable state or depending on execution order
- Tests that sleep or rely on wall-clock timing instead of deterministic control
- Mocks that are so broad they verify nothing (e.g., mocking the function under test)
- Tests marked skipped or xfail without a documented reason — is that tech debt?

### Suspicious tests

- Tests that never actually ran (e.g., misnamed so the runner ignores them)
- Tests that are identical copies of each other
- Tests referencing functions that no longer exist

## Diff-Focused Audit (incremental mode)

When the user asks to audit only recent changes:

1. Get the change scope (git diff against the base, or the file/feature list the user provides).
2. Run only the tests covering the changed areas, plus coverage for those files.
3. Focus the report on: are the changed paths tested? Are new branches covered? Did the change leave stale tests?

This mode keeps cost proportional to the change — use it for large projects or quick checks.

## Coverage Is Not the Goal

A high percentage does not make tests good, and a low percentage on well-tested code can be misleading.

- Coverage tells you *what ran*, not *what was verified*.
- Judge each finding by the scenario: is this behavior worth locking down? Is the assertion strong enough to catch a real regression?
- Report coverage numbers with the tool used and its scope, but never recommend "add tests to raise coverage" for its own sake.

## Report Format

```
## Test Audit Report

**Suite status**: {pass}/{fail}/{skip} | **Coverage**: {percentage} ({tool}, scope)

### Summary
{2-3 sentence overall assessment}

### Findings

#### [P0] {Title}
**Evidence**: {exact test output / file:line}
**Why it matters**: {what could regress unnoticed}
**Fix**: {concrete, test-driven suggestion}

#### [P1] {Title}
...

### Strengths
{what the suite does well — keep it short}
```

Severity levels:

- **P0** — Suite fails, critical path untested, or a test would pass while the feature is broken. Must address.
- **P1** — Significant gap or weak assertion that could hide regressions. Should address.
- **P2** — Quality improvement that lowers maintenance cost. Optional.

## When to Use

Use when the user asks to audit, review, or check test quality, coverage, or test maintenance. Complement, not replace, `code-review`: code review audits the code; test audit audits the tests.
