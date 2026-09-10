---
name: skill-evolution-patcher
description: "Conversational skill self-evolution, feedback-driven rule patching, and dynamic SKILL.md in-place updating protocol with security guardrails and hot-reload hooks."
version: "1.0.0"
category: "architecture"
tags:
  - self-evolution
  - skill-patcher
  - rule-patching
  - feedback-learning
  - dynamic-skills
  - hermes-agent
allowed-tools:
  - file_write_tool
  - file_read_tool
  - file_edit_tool
---

# Conversational Skill Self-Evolution & Rule Patching Protocol (基于自然语言反馈的技能自进化与定点规则修补协议)

## Bash execution contract

When calling `bash_code_execute_tool`, always pass **`reason`** (≥10 characters: why this command runs) and **`command`**. Put `reason` first.


## Overview

Based on lessons from the Hermes Agent skill lifecycle patterns (Chapter 4, Case 5), this skill establishes an automated, safe **Self-Evolution & Rule Patching Pipeline**.
It allows an Agent to continuously absorb explicit conversational corrections (e.g. *"Remember: always generate tables with currency symbols"*, *"Never use raw pointers in generated C++"*) and compile them directly into persistent `SKILL.md` rule sets without manual file editing by human operators.

---

## 1. The 4-Phase Self-Evolution Pipeline

```
[Conversational Correction] ──> [1. Intent Capture & Target Resolution]
                                              │
                                              ▼
                                 [2. Atomic Patch Generation & Safeguard Gate]
                                              │
                                              ▼
                                 [3. In-Place Rule Patching (Diff Application)]
                                              │
                                              ▼
                                 [4. Hot-Reload & Feedback Confirmation]
```

### Phase 1: Intent Capture & Target Resolution (纠偏意图捕获与技能锚定)
- Detect explicit rule evolution triggers: *"以后..."*, *"记住..."*, *"永远不要..."*, *"更新这个技能的规矩"*.
- Resolve which active skill in the session the rule belongs to (e.g. `office-document`, `code-review`, `data-analysis`).
- If ambiguous, prompt the user for target clarification before touching disk.

### Phase 2: Atomic Patch Generation & Safeguard Gate (差异补丁生成与防越权门禁)
The Agent must synthesize an atomic patch adhering to the following strict safety gates:
1. **Tool Privilege Escalation Prohibited (严禁越权修改工具链)**:
   - Frontmatter `allowed-tools` is strictly **IMMUTABLE** via self-evolution. Any attempt to add dangerous tools (e.g. `bash_code_execute_tool`) is blocked.
2. **Safety Baseline Rules Non-Deletable (核心安全基线不可删除)**:
   - Existing safety constraints cannot be loosened or deleted; only additive refinements or tighter restrictions are allowed.
3. **Evolution Lock Check (自进化锁定检查)**:
   - If the skill frontmatter contains `evolution_locked: true`, reject modification and inform the user.

### Phase 3: In-Place Rule Patching (定点原子修改)
- Read current `SKILL.md`.
- Locate the target section (e.g. `## Rules`, `## Quality Checklist`, or `## Negative Constraints`).
- Apply the patch using deterministic search-and-replace or targeted append.
- Record git diff or SHA-256 signature for auditability.

### Phase 4: Hot-Reload & Feedback Confirmation (热重载与闭环确认)
- Trigger the Skill Registry in-memory cache eviction or notify the runtime.
- Respond to the user with a standardized Rule Patch Card:
  - **Target Skill**: `office-document`
  - **Added Rule**: `[Rule-202609-01] All currency metrics must explicitly indicate currency symbol ($/¥/€).`
  - **Status**: Persisted & Effective immediately in future turns.

---

## 2. In-Place Modification Example

### User Trigger
> *"Agent，以后写任何 Python 脚本，都必须在开头加上类型检查说明，并且禁止使用 global 变量。"*

### Generated Patch
```markdown
## Python Code Quality Constraints (Added via Self-Evolution 2026-09-10)
- [x] Must include explicit Type Hints (`typing`) across all function signatures.
- [x] Global variables (`global ...`) are strictly prohibited in user-facing scripts.
```

---

## 3. Pre-flight Verification Gate

Before committing the updated `SKILL.md`:
- [ ] Frontmatter YAML remains valid and correctly delimited with `---`.
- [ ] No tools were added to `allowed-tools`.
- [ ] File size does not exceed the 500-line ceiling.
- [ ] The change is additive or tightening, not destructive.
