---
name: sesa-veriskill-evolution-gate
description: "Self-evolving skill memory with 4-way causal failure attribution, Help-Hurt net-score pruning, and executable unit test verification gates (SESA & VeriSkill)."
version: "1.0.0"
category: "engineering"
tags:
  - self-evolution
  - skill-memory
  - attribution-filter
  - veriskill
  - test-gate
allowed-tools:
  - file_write_tool
  - file_read_tool
  - bash_code_execute_tool
---

# SESA & VeriSkill: Evolving Skill Memory & Executable Attribution Gate (SESA/VeriSkill 演化技能记忆与可执行归因门禁)

## Bash execution contract

When calling `bash_code_execute_tool`, always pass **`reason`** (≥10 characters: why this command runs) and **`command`**. Put `reason` first.


## Overview

A cutting-edge meta-intelligence skill inspired by top-tier academic breakthroughs: **SESA** (arXiv:2607.29468) and **VeriSkill** (arXiv:2607.27733).

In unconstrained self-evolution, agents frequently suffer from **Negative Transfer (负向迁移)**:
- Hallucinated lessons are persisted based on random luck.
- Contradictory rules bloat the prompt.
- The agent gets worse over time instead of improving.

This skill establishes an audit-grade **Executable Attribution & Net-Score Verification Gate**.

---

## 4-Stage SESA & VeriSkill Evolution Protocol (四阶演化门禁流水线)

```
[Stage 1: 4-Way Causal Failure Attribution (四分类因果归因解耦)]
  - When an execution trace fails, mathematically classify the root cause into exactly one bucket:
    ├── Category A: Model Intrinsic Capability Deficit (模型基础能力不足 -> 不可转为技能经验)
    ├── Category B: Tool Execution Exception (外部环境网络/超时波动 -> 属于瞬态重试问题)
    ├── Category C: User Ambiguity / Invalid Prompt (用户输入歧义 -> 属于澄清问题)
    └── Category D: Skill SOP / Instruction Flaw (技能引导规约缺陷 -> 唯一合法的演化输入!)
         ↓
[Stage 2: Help-Hurt Net-Score Pruning (净胜分量化淘汰机制)]
  - Candidate evolutionary rules must maintain a statistical ledger:
    - Score = `help_count` (成功助力次数) - `hurt_count` (导致倒退次数)
  - Net score < +3 after 5 benchmark runs results in immediate automated eviction
         ↓
[Stage 3: VeriSkill Executable Benchmark Gate (可执行物理断言门禁)]
  - NO rule is merged based solely on LLM self-reflection
  - A deterministic test case (`test_evolution_case.py`) must run in sandbox with exit code 0
  - Verifies that fixing Edge Case X does NOT break Baseline Y
         ↓
[Stage 4: Immunized Skill Memory Persistence (抗体型技能记忆固化)]
  - Append the verified lesson to the skill's embedded `learnings.md`
  - Emit an Evolution Audit Certificate
```

---

## Evolution Audit Certificate Contract (`docs/audits/evolution-cert-{slug}.md`)

```markdown
# 技能自演化可执行归因认证 (Evolution Audit Certificate)

- **目标技能**: `financial-report-analyzer`
- **提议演化规则**: "当解析包含多币种合并报表时，必须显式调用汇率标准化函数，严禁在同一列累加原币金额"
- **归因审查结果**: **Category D (技能规约缺陷)** · 归因置信度: **98.2%**

---

## 一、Help-Hurt 历史净胜分评估 (Net Score Ledger)

| 评估指标 | 历史统计 | 阈值标准 | 判定 |
|---|---|---|---|
| 助力成功次数 (`help_count`) | 12 次 | >= 5 | ✅ 通过 |
| 导致回退次数 (`hurt_count`) | 0 次 | <= 1 | ✅ 零回归 |
| **净胜分 (`Net Score`)** | **+12 分** | **>= +3 分** | 🏆 准予合并 |

---

## 二、VeriSkill 物理断言测试结果 (Executable Verification)
- **执行命令**: `pytest tests/eval/test_multicurrency_reconciliation.py`
- **执行退出码**: `exit_code: 0` (100% Passed · 6/6 test assertions)
- **回归验证**: 原始基线单币种测试套件 24/24 全部保持通过。

---

## 三、固化状态
- **持久化路径**: `assets/prebuilt_skills/financial-report-analyzer/learnings.md`
- **免疫生效**: 即刻进入该技能的执行前必读（Read-Before-Action）防线。
```

---

## Operational Safeguards
- **Zero Subjective Reflection**: Discard any proposed rule that lacks an accompanying executable test assertion.
- **Strict Net Positive**: Immediately prune any rule whose `hurt_count` exceeds 1.
