---
name: test-driven-development
description: >-
  Enforce the RED-GREEN-REFACTOR cycle for all code changes. Tests come first,
  code follows. Prevents untested code from entering the codebase.
version: 1.0.0
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
  potential_traps:
    - description: "Writing production code before the test, then retroactively testing"
      mitigation: "Delete any production code written before a test. Start fresh from tests."
      severity: high
    - description: "Writing tests that are too broad or test implementation details"
      mitigation: "Each test should verify ONE behavior. Test the public API, not internals."
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

## Bug Fix TDD

For bug fixes, TDD is especially valuable:

1. **RED:** Write a test that reproduces the bug (fails now)
2. **GREEN:** Fix the bug (test passes)
3. The test now serves as a regression guard forever
