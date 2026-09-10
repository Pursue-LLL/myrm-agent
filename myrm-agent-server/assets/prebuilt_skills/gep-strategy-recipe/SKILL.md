---
name: gep-strategy-recipe
description: >-
  Context-adaptive Strategy Recipe Network based on the GEP (Gene-Environment-Phenotype)
  protocol. Formalizes agent problem-solving patterns into Strategy Gene, Environment Capsule,
  and Audit Trace triplets. Allows agents to index, match, inherit, and evolve proven execution
  recipes across complex, non-deterministic tasks to dramatically improve success rates.
version: 1.0.0
category: workflow-orchestration
tags:
  - gep-protocol
  - strategy-recipe
  - genetic-evolution
  - adaptive-reuse
  - self-evolving-agent
  - 策略配方网络
  - 基因进化协议
  - 上下文自适应复用
allowed-tools: file_read_tool file_write_tool memory_save_tool memory_search_tool bash_code_execute_tool
contract:
  steps:
    - "Phase 1: Environment Capsule Fingerprinting — capture OS, dependencies, dataset scale, rate limits, and authentication profiles into a normalized fingerprint"
    - "Phase 2: Strategy Recipe Indexing & Matching — query Strategy Recipe Network for the closest historical match using topological fingerprint similarity"
    - "Phase 3: Recipe Operator Inheritance — instantiate the selected Strategy Gene operators (phased probing, bisecting triage, multi-source cross-verification)"
    - "Phase 4: Execution Trace Scoring & Gene Evolution — evaluate execution outcome against success rubric and emit an evolved Recipe triplet"
  potential_traps:
    - description: "Blindly executing a historical strategy gene without validating the current environment capsule constraints"
      mitigation: "Strictly enforce Phase 1 fingerprint validation: if compatibility score < 0.75, fall back to safe conservative exploratory mode"
      severity: high
    - description: "Polluting the Strategy Recipe Network with trivial or one-off failure traces"
      mitigation: "Only persist recipes that achieve verified task completion (DoD passed) with a positive success delta"
      severity: medium
  verification_steps:
    - step_id: capsule_fingerprint_valid
      description: "Ensure environment capsule includes os, runtime, dependencies, and constraint markers"
      validation_method: "Verify JSON capsule schema contains required keys"
      is_required: true
    - step_id: strategy_triplet_emitted
      description: "Verify output contains Strategy Gene, Environment Capsule, and Audit Trace blocks"
      validation_method: "Confirm présence of all 3 GEP components in the execution report"
      is_required: true
  success_criteria: "A formal GEP Strategy Recipe deliverable with environment fingerprinting, reusable operators, and verified success trace"
  estimated_duration_seconds: 600
---

# GEP Strategy Recipe Network & Context-Adaptive Reuse Engine

The `gep-strategy-recipe` skill implements the **Genetic Evolution Protocol (GEP)** for AI Agents. It decouples *tactical problem-solving intelligence* from static prompts, representing successful agent behaviors as modular, reusable **Strategy Recipes**.

---

## 1. The GEP Triplet Architecture

Every strategy recipe in the network is represented as an atomic triplet:

$$\text{Recipe} = \langle \text{Strategy Gene}, \text{Environment Capsule}, \text{Audit Trace} \rangle$$

```
┌────────────────────────────────────────────────────────┐
│                   Strategy Recipe                      │
├────────────────────┬───────────────────┬───────────────┤
│   Strategy Gene    │Environment Capsule│  Audit Trace  │
│  (策略解题基因)    │  (环境上下文胶囊) │ (审计与因果链)│
│                    │                   │               │
│ • 算子执行序列     │ • 操作系统/平台   │ • 验证得分    │
│ • 决策分叉点       │ • 依赖包版本      │ • Token/耗时  │
│ • 异常回退规约     │ • 数据规模与限流  │ • 成功因子    │
└────────────────────┴───────────────────┴───────────────┘
```

---

## 2. Standard Strategy Gene Operators

A Strategy Gene is composed of verified modular operators:

1. **Phased Probing (阶段式轻量探测)**:
   在执行昂贵或不可逆操作前，优先使用极轻量命令（如 `head`, `ls`, ping）探测目标环境连通性与权限状态。
2. **Bisecting Triage (二分法断点排查)**:
   在面对长链路或复杂数据管道失败时，自动在链路中间点插桩（Instrumentation）快速缩小故障范围。
3. **Multi-Source Cross-Verification (多源交叉论证)**:
   针对非确定性输出，强制比对至少两组独立数据源或校验工具输出。
4. **Constrained Backtracking (受限局部回退)**:
   当分支尝试超过最大容忍轮次（如 3 轮）未取得进展时，严格回滚至最近检查点状态，避免陷入局部最优陷阱。

---

## 3. Standard Delivery Contract

Whenever this skill executes, output structured results adhering to the following schema:

```markdown
## GEP 策略配方交付包 (Strategy Recipe Package)

### 1. 环境胶囊 (Environment Capsule)
- **平台环境**: macOS Darwin 25.5.0 / Python 3.13 / Node 20.x
- **依赖指纹**: `fastapi>=0.110.0`, `pydantic>=2.7.0`, `sqlite3`
- **规模与限制**: 500+ 文件规模代码库，无外网直接访问沙箱

### 2. 策略基因 (Strategy Gene: `gene_bisect_ast_audit_v2`)
- **适用场景**: 大型代码库多文件重构与契约同步
- **核心算子流**:
  1. `Phased Probing`: 静态扫描变更接口影响面拓扑；
  2. `Bisecting Triage`: 逐个模块运行测试组定位首个断裂点；
  3. `Local Repair`: 应用局部无损修改；
  4. `Cross-Verification`: 运行全量架构守卫与 Lint 检测。

### 3. 审计事件流 (Audit Trace)
- **初始正确率**: 28.5%
- **继承配方后提升**: 85.7% (+57.2%)
- **因果归因**: 通过二分插桩排查，阻断了重复读取与测试僵尸进程。
```
