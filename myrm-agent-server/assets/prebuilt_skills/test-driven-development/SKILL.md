---
name: test-driven-development
description: >-
  Enforce the RED-GREEN-REFACTOR cycle for all code changes. Tests come first,
  code follows. Prevents untested code from entering the codebase.
version: 1.2.0
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
    - "VERIFY — Run the mutation check: mentally mutate the production code and confirm at least one test fails for each realistic break"
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
    - description: "Computing the expected value with the code under test (mirror assertion)"
      mitigation: "Derive expectations by hand with literals or checked fixtures; never reuse the code's own logic"
      severity: high
    - description: "Testing constants or private structure so tests break on every intentional change"
      mitigation: "Assert the behavior that depends on the decision, not the decision itself"
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
    - step_id: expectations_derived_independently
      description: "Every expected value is derived without the code under test"
      validation_method: "Confirm each expectation is a literal or a hand-checked fixture"
      is_required: true
    - step_id: mutation_check_covered
      description: "At least one test fails for each realistic mutation of the production code"
      validation_method: "Mentally mutate constants, branches, state changes, defaults, and input validation"
      is_required: true
  success_criteria: "All tests pass, expectations are derived independently, each test verifies exactly one behavior and survives the mutation check"
  estimated_duration_seconds: 1200
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
- "The test passes immediately" → You're testing existing behavior. Fix the test to fail first.
- "Can't explain why test failed" → Stop. Figure out the failure cause first; a test you can't explain protects nothing.

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

### Derive Expectations Independently

Never compute the expected value with the code under test. A mirror assertion
passes no matter what the code does — it can never fail, so it protects nothing.

```python
# Bad: the same builder computes both sides — always true
expected = build_search_query({"tag": "urgent"})
assert build_search_query({"tag": "urgent"}) == expected

# Good: hand-derived literal
assert build_search_query({"tag": "urgent"}) == 'tag:"urgent"'
```

Table-driven tests with literal `want` values are the preferred shape.

### No Change Detectors

A test that only fails on intentional decisions — a constant's value, exact
message wording, private structure — fires on redesign and sleeps through bugs.
Test the behavior that depends on the decision, not the decision itself.

```python
# Bad: change detector — breaks on any refactor, catches no bug
assert MAX_RETRIES == 5

# Good: tests the behavior that depends on the decision
#   "a failing call is retried 5 times and the 6th attempt never happens"
```

### Mutation Check

Before finishing, mentally mutate the production code. At least one test
should fail for each realistic mutation:

- Wrong constant or argument
- Wrong branch handler
- Missing state change or side effect
- Empty or default return
- Missing validation for zero, empty, nil, unauthorized, or malformed input

A mutation nothing catches marks the behavior as unprotected — or the test as
tautological. Fix the test before moving on.

### Avoid Horizontal Slices

Do not write all tests first, then all implementation. That produces brittle
tests designed before the interface is understood. Work in vertical tracer
bullets instead — one end-to-end behavior slice at a time:

```
WRONG:  RED: test1,test2,test3,test4  →  GREEN: impl1,impl2,impl3,impl4
RIGHT:  test1→impl1 → test2→impl2 → test3→impl3
```

### Gate Function

Before writing the test body, name the production change that would make it
fail. Then confirm the expected value is derived without the code under test.

```
Cannot name a failing change        → redesign around an observable behavior
"The source text changed"           → run the artifact and assert its effects
Only intentional decisions fail it  → it is a change detector; test the behavior
Expected value uses the code under test → replace with a literal or hand-checked fixture
```

### Deeper Reference

For mock discipline, anti-pattern warnings, and a quick-reference table, read
`references/writing-good-tests.md` from this skill when writing or changing tests.

## Bug Fix TDD

For bug fixes, TDD is especially valuable:

1. **RED:** Write a test that reproduces the bug (fails now)
2. **GREEN:** Fix the bug (test passes)
3. The test now serves as a regression guard forever
