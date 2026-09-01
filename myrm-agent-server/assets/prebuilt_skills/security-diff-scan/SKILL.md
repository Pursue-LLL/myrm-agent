---
name: security-diff-scan
description: >-
  Agentic codebase and diff vulnerability scan using verify-then-report.
  Extracts AST syntax slices, constructs minimal dynamic PoC payloads in sandbox,
  and outputs deterministic, zero-false-positive security findings.
version: 1.0.0
category: security
tags:
  - security-scan
  - diff-scan
  - poc-verification
  - vulnerability
allowed-tools: file_read_tool grep_tool glob_tool bash_code_execute_tool
contract:
  steps:
    - "Phase 1: Diff & AST Slice — inspect git unified diff and extract direct caller/callee context (<=300 lines)"
    - "Phase 2: Threat Detection — identify candidate injection (CWE-89/78), path traversal (CWE-22), auth bypass, or secret leaks (CWE-798)"
    - "Phase 3: Sandbox PoC Verification — write and execute minimal isolated proof-of-concept test script in sandbox"
    - "Phase 4: Output & Fingerprint — report only verified findings with deterministic fingerprint, CWE, and remediation guidance"
  potential_traps:
    - description: "Reporting purely speculative or unverified static warnings as blockers (False Positives)"
      mitigation: "Strictly enforce Verify-then-Report: construct a runnable sandbox PoC before reporting Critical/High findings"
      severity: high
    - description: "Executing destructive PoC payloads against production or primary workspace data"
      mitigation: "Run PoC validation in isolated temporary/shadow test files with read-only/mock targets"
      severity: high
    - description: "Flooding prompt context with entire unindexed repositories"
      mitigation: "Slice AST context to only modified functions and immediate call hierarchy (<=300 lines)"
      severity: medium
  verification_steps:
    - step_id: diff_extracted
      description: "Git diff and relevant AST slices extracted cleanly"
      validation_method: "Changed symbols and line ranges identified"
      is_required: true
    - step_id: poc_verified
      description: "Candidate exploits validated dynamically in sandbox"
      validation_method: "PoC execution outputs reproducible exploit evidence"
      is_required: true
    - step_id: findings_fingerprinted
      description: "Each finding structured with CWE and fingerprint hash"
      validation_method: "Matches FindingItem schema with remediation snippet"
      is_required: true
  success_criteria: "All real vulnerabilities verified via sandbox PoC with 0% false positives, structured remediation guidance, and CWE classification."
  estimated_duration_seconds: 600
---

# Security Diff Scan (Verify-then-Report)

## Core Protocol: Verify-then-Report

Never report unproven security warnings as high-severity blockers. Follow the four-stage verification cycle:

```
GIT DIFF / AST SLICE ➔ CANDIDATE THREAT ➔ SANDBOX PoC ATTEMPT ➔ VERIFIED FINDING
```

### Phase 1: AST Slicing & Scope Control
1. Run `git diff -U3` or inspect specified target files.
2. For each changed function or endpoint, extract only:
   - The modified lines.
   - Input entrypoints (parameters, request bodies, query params).
   - Sensitive sinks (SQL queries, subprocess executions, file opens, deserializers).
3. Keep the prompt context under 300 lines per slice to maximize prompt cache hits.

### Phase 2: Threat Modeling
Check for common AI-introduced vulnerability patterns:
- **CWE-89 (SQL Injection)**: String formatting/f-strings inside query builders or raw SQL.
- **CWE-78 (Command Injection)**: `shell=True` or unescaped string concatenation in subprocess calls.
- **CWE-22 (Path Traversal)**: User-controlled file paths without `os.path.abspath` or traversal guards.
- **CWE-798 (Hardcoded Credentials)**: Bare API keys, bearer tokens, or private secrets in code.
- **CWE-285 (Improper Authorization)**: Unprotected routes or missing permission decorators on sensitive endpoints.

### Phase 3: Sandbox PoC Construction
1. Create a minimal, self-contained test script in the sandbox (e.g., `test_poc_<rule>.py`).
2. Simulate the exploit payload against the function or route:
   - Input: malicious string containing quotes, directory traversals, or crafted tokens.
   - Assertion: Check if the unescaped payload bypasses security boundaries.
3. Execute the script with `bash_code_execute_tool` under a strict timeout (<=10s).
4. **Evidence Rule**:
   - If exploit payload succeeds (returns unauthorized data/executes command) ➔ Mark as **VERIFIED**.
   - If exploit payload fails or is rejected ➔ Discard or downgrade to Informational.

### Phase 4: Structured Output

For every confirmed finding, output in structured format:

```markdown
### [SEVERITY] <Title> (<CWE-ID>)
- **Location**: `<file_path>:<line_range>`
- **Fingerprint**: `<hash>`
- **PoC Evidence**:
  ```text
  <reproducible stdout/stderr output>
  ```
- **Remediation**:
  ```python
  <minimal safe replacement code>
  ```
```

## Bash execution contract

Every `bash_code_execute_tool` call must include a clear `reason` parameter explaining the purpose of running the isolated sandbox test script or AST extraction. All sandbox executions must operate on temporary files or isolated mocks and finish within 10 seconds.
