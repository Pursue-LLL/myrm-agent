---
name: ast-grep-search
description: >-
  Structural syntax-aware AST code search, pattern matching, and refactoring using ast-grep (sg).
  Enables precise code discovery ignoring formatting and comments, multi-language support (TypeScript, Python,
  Rust, Go, Java, C++), safe metavariable replacement ($VAR, $$$ARGS), and non-destructive dry-run refactoring.
version: 1.0.0
category: engineering
tags:
  - ast-grep
  - code-search
  - structural-search
  - refactoring
  - static-analysis
allowed-tools:
  - bash_code_execute_tool
  - file_read_tool
  - file_write_tool
contract:
  steps:
    - "Phase 1: Environment & Tool Selection — Verify ast-grep availability (`which ast-grep || which sg`) and determine if query requires AST vs ripgrep"
    - "Phase 2: Pattern Formulation — Formulate AST pattern using metavariables ($VAR, $$$ARGS) or multi-rule YAML definition"
    - "Phase 3: Non-destructive Dry-Run — Execute `ast-grep scan` without file writes to audit match count and locations"
    - "Phase 4: Verified Execution & Refactoring — Apply rewrite rules if requested, validating code syntax integrity after mutation"
  potential_traps:
    - description: "Using regex for code refactoring with multiline arguments, accidentally breaking syntax"
      mitigation: "Always use ast-grep AST matching and metavariables ($$$ARGS) rather than fragile regex substitutions"
      severity: high
    - description: "In-place file mutation without dry-run preview"
      mitigation: "Always run non-destructive search first, inspect matched diffs before running write/rewrite"
      severity: high
  verification_steps:
    - step_id: ast_metavariables_used
      description: "Verify that AST pattern leverages $VAR or $$$ARGS metavariables for syntax-tree-aware extraction"
      validation_method: "Inspect pattern for valid ast-grep metavariable syntax ($VAR, $$$ARGS)"
      is_required: true
    - step_id: non_destructive_first
      description: "Verify that initial search is strictly read-only and non-destructive before executing refactoring rewrite"
      validation_method: "Ensure dry-run scan precedes any write or rewrite operation"
      is_required: true
---

# AST-Grep Structural Code Search Skill (ast-grep-search)

## Bash execution contract

When calling `bash_code_execute_tool`, always pass **`reason`** (≥10 characters: why this command runs) and **`command`**. Put `reason` first.


A specialized engineering skill for performing **Structural syntax-aware AST code search**, pattern matching, and refactoring using **ast-grep (`sg`)**.

## 1. Concrete Syntax Tree vs Regex Search

Unlike plain-text regex tools (e.g. `ripgrep`), `ast-grep` parses source code into a **Concrete Syntax Tree** (CST / AST):
- **Layout Insensitive**: Matches patterns regardless of whitespace, line breaks, indentation, or trailing commas.
- **Comment Tolerant**: Ignores comments inside expressions without triggering false positives.
- **Syntactic Structure Matching**: Matches complete semantic AST constructs (e.g. function calls, try-catch blocks, decorator chains).
- **Metavariable Capture**: Captures nodes into `$VAR` (single AST node) and `$$$ARGS` (multi-node sequence).

### When to use ast-grep vs ripgrep

| Scenario | Recommended Tool | Rationale |
|---|---|---|
| Simple string literals, keywords, file paths | `ripgrep` (`rg`) | Blazing fast raw string search |
| Multiline function calls with unknown arguments | `ast-grep` (`sg`) | Concrete Syntax Tree ignores newlines |
| Find missing error logging in catch blocks | `ast-grep` (`sg`) | Syntactic tree query with relational rules |
| Safe identifier / API signature refactoring | `ast-grep` (`sg`) | Metavariable capture `$VAR` and rewrite |

---

## 2. Core Metavariable Conventions

- **`$VAR`**: Matches any single AST node (variable identifier, literal, single expression).
  - Example: `const $VAR = require($MOD)`
- **`$$$ARGS`**: Matches zero or more contiguous AST nodes (argument lists, parameter lists, statement blocks).
  - Example: `logger.error($$$ARGS)`

---

## 3. Refactoring & Safe Rewrite SOP

Follow this strict 4-step execution flow for all structural code modifications:

1. **Check Environment**:
   ```bash
   which ast-grep || which sg || npm i -g @ast-grep/cli
   ```
2. **Read-Only Dry Run**:
   ```bash
   ast-grep scan --pattern 'console.log($$$ARGS)'
   ```
3. **Draft Rewrite Pattern**:
   ```bash
   ast-grep scan --pattern 'fetchData($ID, function() { $$$BODY })' \
     --rewrite 'const $DATA = await fetchDataAsync($ID); $$$BODY'
   ```
4. **Post-Rewrite Verification**:
   Run linters and tests to verify that the transformed code is syntactically sound.
