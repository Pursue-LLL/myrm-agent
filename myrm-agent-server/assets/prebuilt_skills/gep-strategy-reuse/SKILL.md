---
name: gep-strategy-reuse
description: "Gene-Environment-Phenotype (GEP) strategy recipe network and context-adaptive reuse protocol. Distills task-solving patterns into immutable Strategy Genes and executes adaptive reuse across shifting runtime environments."
version: "1.0.0"
category: "engineering"
tags:
  - gep-protocol
  - strategy-gene
  - adaptive-reuse
  - evox
  - evomap
  - strategy-recipes
allowed-tools:
  - file_write_tool
  - file_read_tool
  - memory_save_tool
  - memory_search_tool
---

# GEP Strategy Recipe Network & Context-Adaptive Reuse Protocol (基于 GEP 协议的策略基因网络与自适应复用)

## Bash execution contract

When calling `bash_code_execute_tool`, always pass **`reason`** (≥10 characters: why this command runs) and **`command`**. Put `reason` first.


## Overview

Based on the Gene-Environment-Phenotype (GEP) protocol (arXiv:2604.15097), this skill decouples problem-solving intelligence into a formal triad:
1. **Strategy Gene ($G$)**: The pure, variable-free algorithmic skeleton and decision logic.
2. **Environment Capsule ($E$)**: The runtime constraints, OS architecture, dependencies, and state preconditions.
3. **Audit Phenotype ($P$)**: The observable outcome, performance benchmark, and verification proof.

This prevents the pervasive problem where agents forget effective solution patterns across sessions or blindly copy-paste brittle scripts that fail when environmental variables subtly drift.

---

## 1. The Strategy Gene Schema (`gep_recipe.yaml`)

```yaml
gep_strategy_recipe:
  gene_id: "STRAT-DEBUG-MEMORY-LEAK-V1"
  version: "1.0.0"
  intent_family: "runtime_performance_troubleshooting"
  
  # 1. Environment Capsule Constraints (前置环境准入胶囊)
  environment_capsule:
    runtime: "python >= 3.10"
    process_access: "psutil_or_procfs"
    memory_pressure_threshold_pct: 80

  # 2. Strategy Gene Pipeline (纯逻辑策略步骤)
  pipeline:
    - step: 1
      action: "sample_resident_set_size_growth"
      tool: "bash_code_execute_tool"
      retry_policy: { max_attempts: 3, backoff_factor: 1.5 }
    - step: 2
      action: "dump_heap_snapshots_differencing"
      tool: "bash_code_execute_tool"
    - step: 3
      action: "isolate_growing_object_references"
      tool: "bash_code_execute_tool"

  # 3. Context-Adaptive Mutation Rules (自适应变异规则)
  adaptation_rules:
    - condition: "docker_cgroup_v2_detected"
      mutation: "switch from psutil to /sys/fs/cgroup/memory.current"
    - condition: "heap_dump_denied_due_to_disk_space"
      mutation: "fallback to sampling GC tracemalloc top 10 allocators in-memory"

  # 4. Phenotype Verification Benchmark (表型验收基准)
  phenotype_proof:
    success_criterion: "identified_leak_root_cause_with_diff_bytes"
    required_evidence: "top_allocating_file_and_line_number"
```

---

## 2. The 3-Stage GEP Operational Cycle

```
[Problem Discovery] ──> [1. Match Gene & Environment Capsule]
                                   │
                                   ▼
                        [2. Adaptive Execution with Mutation Rules]
                                   │
                                   ▼
                        [3. Audit Phenotype Proof & Save Feedback]
```

### Stage 1: Gene Matching & Capsule Validation
When a task begins, query `memory_search_tool` for existing `gep_recipe` matching the `intent_family`. Verify that the current runtime satisfies `environment_capsule`.

### Stage 2: Adaptive Execution & Mutation
Execute steps defined in `pipeline`. If an environmental constraint or permission failure occurs, trigger the corresponding `mutation` from `adaptation_rules` without failing the overall turn.

### Stage 3: Phenotype Proof Archival
Validate the physical outcome against `phenotype_proof`. Record execution metrics (duration, tool calls) and commit back to the gene repository to increase fitness score.
