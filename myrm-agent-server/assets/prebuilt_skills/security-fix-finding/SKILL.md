---
name: security-fix-finding
description: >-
  Automated security finding remediation and regression verification.
  Generates minimal security patches for verified findings, replays PoC
  tests to confirm mitigation, and stages verified patches for review.
version: 1.0.0
category: security
tags:
  - security-fix
  - auto-remediation
  - poc-replay
  - vulnerability-fix
allowed-tools: file_read_tool file_write_tool grep_tool glob_tool bash_code_execute_tool
contract:
  steps:
    - "Phase 1: Finding Analysis — inspect verified finding details, affected lines, and PoC test"
    - "Phase 2: Minimal Patch Synthesis — craft minimal defensive fix preserving original business logic"
    - "Phase 3: PoC Replay Verification — re-run the PoC exploit script to verify attack is blocked"
    - "Phase 4: Functional Regression Test — run project unit tests to ensure no regressions"
    - "Phase 5: Stage for Review — format patch description and mark ready for Kanban review"
  potential_traps:
    - description: "Over-fixing or refactoring unrelated code while applying security patches"
      mitigation: "Strictly apply minimal defensive changes targeted specifically at the vulnerable sink"
      severity: high
    - description: "Applying fix without verifying that the original PoC is actually blocked"
      mitigation: "Always replay the verified PoC script; fix is incomplete unless exploit exits with rejection/failure"
      severity: high
    - description: "Breaking existing unit tests or changing public API contracts"
      mitigation: "Run test suite immediately after applying patch before declaring success"
      severity: medium
  verification_steps:
    - step_id: patch_applied
      description: "Defensive fix written to target file cleanly"
      validation_method: "File contains parameterized query, safe path check, or input guard"
      is_required: true
    - step_id: poc_blocked
      description: "Original exploit PoC fails to execute against patched code"
      validation_method: "PoC replay returns 400/403/rejection error code"
      is_required: true
    - step_id: tests_pass
      description: "Existing project test suite passes cleanly"
      validation_method: "Regression test runner completes with exit code 0"
      is_required: true
  success_criteria: "Vulnerability mitigated with 100% PoC blockage, 0 regressions in test suite, staged for user review."
  estimated_duration_seconds: 600
---

# Security Fix Finding (Remediation & PoC Replay)

## Remediation Workflow

```
INSPECT FINDING & PoC ➔ APPLY MINIMAL PATCH ➔ REPLAY PoC (VERIFY BLOCKED) ➔ RUN UNIT TESTS ➔ STAGE
```

### 1. Root Cause & PoC Inspection
- Read the vulnerable source file at the indicated line numbers.
- Inspect the exploit payload and understand why the unescaped sink allowed unauthorized execution.

### 2. Minimal Patching Rules
- **SQL Injection (CWE-89)**: Replace string interpolation with ORM bindings, parameterized placeholders (`?` or `:name`), or prepared statements.
- **Command Injection (CWE-78)**: Replace `shell=True` and string command concatenation with arguments array `subprocess.run(["cmd", arg1, arg2], check=True)`.
- **Path Traversal (CWE-22)**: Resolve absolute path via `os.path.abspath` and verify `path.startswith(base_directory)`.
- **Hardcoded Secret (CWE-798)**: Move plaintext credentials to `os.environ.get()` with appropriate fallback or error handling.

### 3. PoC Replay & Verification
1. Re-run the reproduction PoC script in the sandbox.
2. Verify that:
   - The exploit payload is cleanly rejected (e.g. HTTP 400/403 or exception caught).
   - Sensitive data is no longer leaked.
3. Remove temporary PoC test artifacts after verification.

### 4. Regression & Kanban Staging
- Execute the repo's existing test suite (e.g., `pytest` or `bun test`).
- Summarize the change with:
  - **Vulnerability Remediated**: `<Title> (<CWE>)`
  - **Verification**: `PoC Attack Blocked + All Unit Tests Passing`
  - **Modified Files**: `<file_path>`

## Bash execution contract

Every `bash_code_execute_tool` call must include a clear `reason` parameter explaining the purpose of running the remediation verification script or existing test suite. All executions must operate on temporary test files or minimal test scopes and finish within 10 seconds.
