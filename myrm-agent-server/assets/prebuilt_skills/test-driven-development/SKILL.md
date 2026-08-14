---
name: test-driven-development
description: >-
  Enforce the RED-GREEN-REFACTOR cycle for all code changes. Tests come first,
  code follows. Prevents untested code from entering the codebase.
version: 1.1.0
category: development
tags:
  - testing
  - tdd
  - quality
  - red-green-refactor
allowed-tools: bash_code_execute_tool file_write_tool file_read_tool file_edit_tool grep_tool
contract:
  steps:
    - "RED — Write a minimal failing test that defines the expected behavior"
    - "GREEN — Write the minimum code to make the test pass"
    - "REFACTOR — Clean up the code while keeping tests green"
    - "PRIORITIZE — Layer tests by the test pyramid: unit-first, mock only at necessary boundaries"
  potential_traps:
    - description: "Writing production code before the test, then retroactively testing"
      mitigation: "Delete any production code written before a test. Start fresh from tests."
      severity: high
    - description: "Writing tests that are too broad or test implementation details"
      mitigation: "Each test should verify ONE behavior. Test the public API, not internals."
      severity: medium
    - description: "Mocking everything so tests pass while production breaks"
      mitigation: "Prefer real code over mocks; mock only at slow or non-deterministic boundaries"
      severity: high
    - description: "Writing mostly slow end-to-end tests instead of a balanced pyramid"
      mitigation: "Unit tests for pure logic, integration for boundaries, few E2E for critical flows"
      severity: medium
  verification_steps:
    - step_id: test_fails_first
      description: "The new test fails before any production code is written"
      validation_method: "Run the test and confirm it produces a failure"
      is_required: true
    - step_id: minimal_green
      description: "Only the minimum code needed to pass the test is written"
      validation_method: "No extra features, no premature optimization"
      is_required: true
    - step_id: tests_assert_behavior
      description: "Tests assert behavior state, not internal mock interactions"
      validation_method: "Check each test verifies the real outcome, not which methods were called"
      is_required: true
  success_criteria: "All tests pass, code is clean, each test verifies exactly one behavior"
  estimated_duration_seconds: 900
---

# Test-Driven Development (TDD)


## Bash execution contract

When calling `bash_code_execute_tool`, always pass **`reason`** (≥10 characters: why this command runs) and **`command`**. Put `reason` first.

## The Iron Law

```
NO PRODUCTION CODE WITHOUT A FAILING TEST FIRST
```

Write code before the test? Delete it. Start over. Don't keep it as "reference." Implement fresh from tests.

## The Cycle

### RED — Write Failing Test

Write ONE minimal test showing what should happen:

1. **Describe the behavior**, not the implementation
2. **One assertion per test** — keep it focused
3. **Run the test** — confirm it FAILS with the expected error
4. **Never proceed** until you've seen the test fail

**Action:** Create the test file with `file_write_tool`, then run with `bash_code_execute_tool`:

```bash
pytest tests/test_new_feature.py -v
# Expected: FAILED (1 failure)
```

### GREEN — Write Minimum Code

Write the SIMPLEST code that makes the test pass:

1. **Minimum viable implementation** — no extras, no cleverness
2. **Don't anticipate future tests** — solve only this test
3. **Run ALL tests** — new test passes, existing tests still pass
4. **If a test fails**, fix ONLY that failure

```bash
pytest tests/ -q
# Expected: all passed
```

### REFACTOR — Clean Up

Now that tests are green, improve the code:

1. **Remove duplication** — DRY the production code
2. **Improve naming** — make intent clear
3. **Simplify** — remove unnecessary complexity
4. **Run tests after every change** — stay green

## When to Use

**Always:** New features, bug fixes, refactoring, behavior changes.

**Exceptions (ask user first):** Throwaway prototypes, generated code, configuration files.

## Red Flags

If you catch yourself:
- "Skip TDD just this once" → Stop. That's rationalization.
- "I'll write tests after" → Tests written after code don't test the right things.
- "This is too simple for tests" → Simple code gets complex. Start testing now.
- "I'll test the whole flow instead" → Integration tests don't replace unit tests.

## Writing Good Tests

### Prefer Real Over Mocks

Use the simplest test double that gets the job done:

1. **Real implementation** — highest confidence, catches real bugs
2. **Fake** — in-memory substitute for a dependency (e.g., in-memory DB)
3. **Stub** — returns canned data, no behavior
4. **Mock** — verifies interactions; use only at slow or non-deterministic boundaries (external APIs, email)

Mock everything and tests pass while production breaks. If you must mock everything, the code is too coupled — simplify the design.

### Test State, Not Interactions

Assert the **outcome** of an operation, not which internal methods were called. Interaction-based tests break on refactor even when behavior is unchanged.

```python
# Good: asserts the behavior
assert result.status == "completed"

# Bad: asserts an internal call — breaks on refactor
assert db.query.called_with("ORDER BY created_at DESC")
```

### Test Pyramid

Invest effort by layer — most tests small and fast:

- **Unit tests (~80%)** — pure logic, isolated, milliseconds each
- **Integration tests (~15%)** — component interactions, API boundaries, database
- **E2E tests (~5%)** — critical user flows only; slow and brittle, so keep them few

## Bug Fix TDD

For bug fixes, TDD is especially valuable:

1. **RED:** Write a test that reproduces the bug (fails now)
2. **GREEN:** Fix the bug (test passes)
3. The test now serves as a regression guard forever
