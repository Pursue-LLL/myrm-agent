---
name: systematic-debugging
description: >-
  4-phase root cause debugging workflow. Prevents random fix attempts by enforcing
  systematic investigation: reproduce → trace → hypothesize → fix. Dramatically
  improves first-time fix rate from ~40% to ~95%.
version: 1.0.0
category: development
tags:
  - debugging
  - troubleshooting
  - root-cause
  - investigation
allowed-tools: bash_code_execute_tool file_read_tool grep_tool glob_tool web_search_tool
contract:
  steps:
    - "Phase 1: Root Cause Investigation — read errors, reproduce, check recent changes, trace data flow"
    - "Phase 2: Pattern Analysis — find working examples, compare, identify differences"
    - "Phase 3: Hypothesis & Testing — form single hypothesis, test minimally, verify"
    - "Phase 4: Implementation — create failing test, implement fix, verify no regressions"
  potential_traps:
    - description: "Attempting fixes before completing Phase 1 investigation"
      mitigation: "Enforce the Iron Law: no fixes without root cause investigation first"
      severity: high
    - description: "Testing multiple changes simultaneously, unable to isolate cause"
      mitigation: "One variable at a time; revert if unclear which change helped"
      severity: medium
  verification_steps:
    - step_id: reproduce
      description: "Bug is consistently reproducible with exact steps"
      validation_method: "Run the failing test or trigger the bug reliably"
      is_required: true
    - step_id: root_cause
      description: "Root cause is identified and documented"
      validation_method: "Can explain WHY the bug occurs, not just WHERE"
      is_required: true
    - step_id: regression_test
      description: "All existing tests pass after the fix"
      validation_method: "Run full test suite with zero failures"
      is_required: true
  success_criteria: "Bug is fixed at root cause, regression test passes, no new bugs introduced"
  estimated_duration_seconds: 1800
---

# Systematic Debugging


## Bash execution contract

When calling `bash_code_execute_tool`, always pass **`reason`** (≥10 characters: why this command runs) and **`command`**. Put `reason` first.

## The Iron Law

```
NO FIXES WITHOUT ROOT CAUSE INVESTIGATION FIRST
```

If you haven't completed Phase 1, you cannot propose fixes. Random fixes waste time and create new bugs. Symptom fixes are failure.

## When to Use

Use for ANY technical issue: test failures, production bugs, unexpected behavior, performance problems, build failures, integration issues.

**Especially when:**
- Under time pressure (emergencies make guessing tempting)
- "Just one quick fix" seems obvious
- You've already tried multiple fixes
- You don't fully understand the issue

## Phase 1: Root Cause Investigation

**BEFORE attempting ANY fix:**

### 1. Read Error Messages Carefully

Don't skip past errors or warnings — they often contain the exact solution.

**Action:** Use `file_read_tool` on relevant source files. Use `grep_tool` to find the error string in the codebase.

### 2. Reproduce Consistently

Can you trigger it reliably? What are the exact steps? If not reproducible, gather more data — don't guess.

**Action:** Use `bash_code_execute_tool` to run the failing test:

```bash
# Run specific failing test
pytest tests/test_module.py::test_name -v --tb=long
```

### 3. Check Recent Changes

What changed that could cause this? Git diff, recent commits, new dependencies.

**Action:**

```bash
git log --oneline -10
git diff
git log -p --follow src/problematic_file.py | head -100
```

### 4. Gather Evidence in Multi-Component Systems

For each component boundary: log what data enters, what exits, verify config propagation. Run once to gather evidence showing WHERE it breaks.

### 5. Trace Data Flow

Where does the bad value originate? Keep tracing upstream until you find the source. Fix at the source, not the symptom.

**Action:** Use `grep_tool` to trace references:
- Find where the function is called
- Find where the variable is set
- Follow the call chain upstream

### Phase 1 Completion Checklist

- [ ] Error messages fully read and understood
- [ ] Issue reproduced consistently
- [ ] Recent changes identified and reviewed
- [ ] Evidence gathered (logs, state, data flow)
- [ ] Problem isolated to specific component/code
- [ ] Root cause hypothesis formed

**STOP.** Do not proceed to Phase 2 until you understand WHY it's happening.

## Phase 2: Pattern Analysis

### 1. Find Working Examples

Locate similar working code in the same codebase. What works that's similar to what's broken?

### 2. Compare Against References

Read the reference implementation COMPLETELY. Don't skim — read every line. Understand the pattern fully before applying.

### 3. Identify Differences

List every difference between working and broken, however small. Don't assume "that can't matter."

## Phase 3: Hypothesis & Testing

### 1. Form a Single Hypothesis

State clearly: "I think X is the root cause because Y." Be specific, not vague.

### 2. Test Minimally

Make the SMALLEST possible change to test the hypothesis. One variable at a time. Don't fix multiple things at once.

### 3. Verify Before Continuing

- Worked? → Phase 4
- Didn't work? → Form NEW hypothesis
- DON'T add more fixes on top

### 4. The Rule of Three

If ≥ 3 fixes failed: **STOP and question the architecture.** 3+ failures = architectural problem, not a bug. Discuss with the user before attempting more fixes.

## Phase 4: Implementation

### 1. Create Failing Test Case

Write the simplest possible reproduction as an automated test. MUST have before fixing.

### 2. Implement Single Fix

Address the root cause identified. ONE change at a time. No "while I'm here" improvements. No bundled refactoring.

### 3. Verify Fix

```bash
# Run the specific regression test
pytest tests/test_module.py::test_regression -v

# Run full suite — no regressions
pytest tests/ -q
```

## Red Flags — STOP and Return to Phase 1

If you catch yourself thinking:
- "Quick fix for now, investigate later"
- "Just try changing X and see if it works"
- "I don't fully understand but this might work"
- "One more fix attempt" (when already tried 2+)
- Proposing solutions before tracing data flow

## Common Rationalizations

| Excuse | Reality |
|--------|---------|
| "Issue is simple, don't need process" | Simple issues have root causes too. Process is fast for simple bugs. |
| "Emergency, no time for process" | Systematic debugging is FASTER than guess-and-check thrashing. |
| "Just try this first, then investigate" | First fix sets the pattern. Do it right from the start. |
| "Multiple fixes at once saves time" | Can't isolate what worked. Causes new bugs. |
| "I see the problem, let me fix it" | Seeing symptoms ≠ understanding root cause. |
