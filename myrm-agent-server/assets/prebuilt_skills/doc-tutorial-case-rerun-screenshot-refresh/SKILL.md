---
name: doc-tutorial-case-rerun-screenshot-refresh
description: >-
  Automated tutorial & documentation case rerun workflow with step-by-step screenshot refresh.
  Executes tutorial/demo cases in sandbox, captures standardized 1920x1080 @2x screenshots,
  enforces visual validity & credential redaction, and performs AST block-level in-place image replacement.
version: 1.0.0
category: documentation
tags:
  - tutorial
  - documentation
  - screenshot
  - automation
  - case-rerun
  - feishu
  - markdown
allowed-tools: file_read_tool file_write_tool file_edit_tool glob_tool grep_tool bash_code_execute_tool browser_navigate_tool browser_snapshot_tool browser_extract_tool
contract:
  steps:
    - "Phase 1: Recon & AST Parse — parse target Markdown/MDX or doc structure, extract step markers, code snippets, and image references"
    - "Phase 2: Sandbox Execution — run tutorial/demo case commands in isolated sandbox, monitor stdout/stderr and exit codes"
    - "Phase 3: Standardized Screenshot Capture — render UI in 1920x1080 @2x viewport, apply credential redaction, and capture crisp png"
    - "Phase 4: Visual Assertion & Guard — verify non-blank/non-uniform histogram, check DOM completion selector, and confirm zero crash state"
    - "Phase 5: Block-Level In-Place Replacement & Artifacts — update image references via AST, output side-by-side DIFF-PREVIEW.html"
  potential_traps:
    - description: "Overwriting surrounding text/formatting during image replacement"
      mitigation: "Strictly use AST node-level replacement instead of naive global regex string substitution"
      severity: high
    - description: "Capturing error/white screen due to network or async loading lag"
      mitigation: "Wait for DOM stability/completion selector and check image variance before saving screenshot"
      severity: high
    - description: "Leaking sensitive credentials (API tokens, private keys) in screenshots"
      mitigation: "Apply automated redaction mask over sensitive environment variables and terminal output"
      severity: critical
  verification_steps:
    - step_id: case_execution_success
      description: "Tutorial case script exits with code 0 in sandbox"
      validation_method: "Verify bash command execution exit code"
      is_required: true
    - step_id: screenshot_validity_verified
      description: "All captured screenshots meet resolution and non-blank visual thresholds"
      validation_method: "Check file existence, dimensions (1920x1080 or ratio equivalent), and non-zero byte size"
      is_required: true
    - step_id: ast_atomic_replacement_verified
      description: "Document image references updated without mutating surrounding markdown text"
      validation_method: "Diff document content to ensure only image targets were modified"
      is_required: true
    - step_id: diff_preview_artifact_generated
      description: "Side-by-side visual comparison artifact produced in artifacts/ directory"
      validation_method: "Verify DIFF-PREVIEW.html or comparison summary exists in artifacts/"
      is_required: true
  success_criteria: "All case steps executed successfully, high-definition sanitized screenshots captured, document AST updated in-place, and visual diff artifact generated"
  estimated_duration_seconds: 1200
---

# Doc Tutorial Case Rerun & Screenshot Refresh SOP

## Bash execution contract

When calling `bash_code_execute_tool`, always pass **`reason`** (≥10 characters: why this command runs) and **`command`**. Put `reason` first.

## Overview
This skill provides an end-to-end, zero-hallucination workflow for keeping developer documentation, tutorials, and quickstart guides continuously fresh. When upstream libraries or UI designs evolve, it runs test cases in sandbox, captures pixel-perfect sanitized screenshots, and atomically replaces outdated images in Markdown/MDX or documentation blocks.

## Execution Phases

### Phase 1: Recon & Document AST Parsing
1. Read the target documentation file (`README.md`, `docs/*.md`, `docs/*.mdx`).
2. Identify all step-by-step tutorial milestones:
   - Command blocks to execute (e.g. `npm run dev`, `python app.py`).
   - Image references associated with each step (e.g. `![Step 1](./assets/step1.png)`).
3. Record baseline image paths and locations in the document AST.

### Phase 2: Sandbox Case Execution
1. Set up test environment dependencies in sandbox (e.g. `npm install`, `uv sync`).
2. Execute each step sequentially.
3. For long-running dev servers or UI apps, start in background and await readiness sentinel / health check port.
4. Record stdout/stderr logs and assert clean exit or healthy service status.

### Phase 3: Standardized Screenshot Capture & Redaction
1. Configure browser viewport to standardized dimensions (`1920x1080`, device scale factor `2`).
2. Navigate to target URL/UI state.
3. **Credential Redaction**: Before taking the snapshot, ensure any sensitive tokens, emails, or private keys rendered on screen or in logs are blurred or masked.
4. Capture high-definition `.png` screenshot to workspace assets folder (e.g. `docs/assets/screenshots/`).

### Phase 4: Visual Assertion & Verification Gate
1. Verify screenshot file existence and non-zero size.
2. Confirm the screen is not a blank white screen, 404/500 error page, or crashing state.
3. If step fails, halt progression, diagnose root cause, and retry from the current checkpoint without losing earlier step artifacts.

### Phase 5: Block-Level In-Place Replacement & Artifact Generation
1. Replace image links in target document at the exact AST node level:
   - Keep surrounding headings, bullet points, and explanatory text completely intact.
2. Generate `DIFF-PREVIEW.html` in `artifacts/` folder:
   - Display side-by-side comparison of `Old Screenshot` vs `New Screenshot` for each step.
   - Summarize modified file paths and execution time.
3. Present executive summary to user with artifact preview link.
