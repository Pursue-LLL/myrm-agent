---
name: ast-grep-structural-search
description: >-
  Precision multi-language AST-based structural code search and safe rewrite workflow.
  Uses ast-grep (sg) pattern matching syntax ($PATTERN, $$$ARGS) to locate syntactic
  structures across TypeScript, JavaScript, Python, Rust, Go, Java, and C/C++, avoiding
  regex false positives in comments, strings, and multi-line declarations.
version: 1.0.0
category: development
tags:
  - ast-grep
  - code-search
  - refactoring
  - structural-search
  - pattern-matching
  - rewrite
  - 代码搜索
  - 语法树重构
allowed-tools: bash_code_execute_tool file_read_tool file_write_tool grep_tool glob_tool
contract:
  steps:
    - "Phase 1: Environment & Tooling Verification — Probe availability of `ast-grep` CLI (sg / npx @ast-grep/cli)"
    - "Phase 2: AST Pattern Formulation — Craft precise structural patterns matching syntactic nodes without regex flakiness"
    - "Phase 3: Search Execution & Filtering — Run AST query with target language and path scoping"
    - "Phase 4: Safe Rewrite & Diff Audit (Optional) — When refactoring, preview AST replacements via diff before application"
  potential_traps:
    - description: "Searching with ambiguous patterns matching too broadly across disparate language ASTs"
      mitigation: "Always explicitly specify the target language via --lang flag (e.g. --lang ts / --lang python)"
      severity: medium
    - description: "Uncontrolled batch rewrite without verifying test suite passes"
      mitigation: "Preview diffs first; run unit tests immediately after applying any AST-based code transformation"
      severity: high
    - description: "Missing CLI in minimalist environments"
      mitigation: "Provide automatic fallback: try `sg run` -> `npx @ast-grep/cli run` -> Python AST / ripgrep fallback"
      severity: medium
  verification_steps:
    - step_id: pattern_syntax_valid
      description: "Ensure ast-grep query compiles and matches syntax nodes without parsing errors"
      validation_method: "CLI returns exit code 0 and valid match spans"
      is_required: true
  success_criteria: "Structural code search executed with zero string/comment false positives, delivering precise AST spans and safe rewrites."
  estimated_duration_seconds: 180
---

# ast-grep Structural Code Search & Safe Refactoring

## Bash execution contract

When calling `bash_code_execute_tool`, always pass **`reason`** (≥10 characters: why this command runs) and **`command`**. Put `reason` first.


## Overview

Regular expressions (`grep`, `ripgrep`) operate on flat characters. They struggle with multi-line signatures, nested blocks, and easily confuse real code with comments or string literals.

`ast-grep` parses code into a **Concrete Syntax Tree (CST)**, allowing you to search and rewrite code based on its grammatical structure across 20+ programming languages.

---

## 1. Core Pattern Syntax

- `$VAR`: Matches any single AST node (expression, identifier, type, or parameter).
- `$$$VARS`: Matches zero or more sequential AST nodes (e.g., arguments list, statements block).

### Examples by Use Case

| Language | Target Structure | ast-grep Pattern |
| :--- | :--- | :--- |
| **TypeScript** | `useState` hooks with boolean init | `const [$VAL, $SET] = useState<boolean>($INIT)` |
| **TypeScript** | Try/catch blocks with empty catch | `try { $$$TRY } catch ($E) {}` |
| **Python** | Subprocess calls with `shell=True` | `subprocess.$FUNC($$$ARGS, shell=True, $$$KWARGS)` |
| **Python** | Functions missing type annotations | `def $FUNC($PARAM): $$$BODY` |
| **Rust** | `unwrap()` calls on options/results | `$EXPR.unwrap()` |
| **Go** | Ignored error returns | `$VAL, _ := $FUNC($$$ARGS)` |

---

## 2. Command Execution SOP

### Step 1: Probe Environment & Execute Query

```bash
# Direct binary probe
if command -v sg >/dev/null 2>&1; then
  sg run -p 'const [$VAL, $SET] = useState($INIT)' --lang ts src/
elif command -v npx >/dev/null 2>&1; then
  npx @ast-grep/cli run -p 'const [$VAL, $SET] = useState($INIT)' --lang ts src/
else
  echo "Fallback: Using language-specific AST tools (python -m ast or ripgrep)"
fi
```

### Step 2: Structural Rewrite with Diff Preview

To refactor code across the repository safely:

```bash
# 1. Preview changes (Dry run)
sg run -p 'console.log($$$ARGS)' -r 'logger.debug($$$ARGS)' --lang ts

# 2. Interactive or confirmed application
sg run -p 'console.log($$$ARGS)' -r 'logger.debug($$$ARGS)' --lang ts --rewrite -U
```

---

## 3. Best Practices

1. **Explicit Language Scope**: Always supply `--lang <lang>` to prevent cross-language grammar collisions.
2. **Context Bounding**: Restrict queries to specific directories (e.g. `src/components/`) to minimize memory footprint.
3. **Audit Diffs Before Commits**: Never apply structural rewrites without running `git diff` and project test suites.
