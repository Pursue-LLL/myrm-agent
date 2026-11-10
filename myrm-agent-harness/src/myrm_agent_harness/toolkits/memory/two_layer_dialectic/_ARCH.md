# two_layer_dialectic/

## 架构概述

两层上下文注入与多遍辩证推理调和套件（Two-Layer Context Injection & Multi-Pass Dialectic Reconciliation Suite）。

### 核心机制
1. **Layer 1: Base Context 极简低频基础层**：
   由 Session Summary 与 Peer Card 构成，依据 `context_cadence` 低频刷新；输出是挂在 User Message 尾部的 XML 块，System Prompt 保持不变。
2. **Layer 2: Dialectic Reasoning 辩证推理调和层**：
   识别记忆陈述之间的冲突，按 1~3 遍（Pass 0 审查 -> Pass 1 综合 -> Pass 2 调和）给出以后一条陈述为准的调和结果；全程是确定性规则，不调用 LLM。
3. **使用方**：只有 Lab/API（`/memory/two-layer-dialectic/*`）调用；没有任何对话轮次注入 `<base_context>` 或辩证块。
4. **三大正交调优旋钮**：
   - `context_cadence`：基础上下文刷新间隔轮次；
   - `dialectic_cadence`：辩证推理触发间隔轮次；
   - `dialectic_depth`：辩证推理深度（1~3 遍）；
   - `dialectic_reasoning_level`：算力等级（fast/standard/deep），只随配置携带，目前没有代码按它分配算力。

## 文件清单

| 文件 | 角色 | 职责 | I/O/P |
| --- | --- | --- | --- |
| `models.py` | 实体模型 | 定义 DialecticCadenceConfig, BaseContextBundle, ConflictItem, DialecticReconciliationResult, TwoLayerContextInjectionResult | ✅ |
| `injector.py` | 上下文注入 | 两层上下文注入器：按 cadence 编译并缓存 Layer 1，按需调用调和器生成 Layer 2，输出 XML 格式的尾部挂载块，保护 System Prompt KV Cache | ✅ |
| `reconciler.py` | 推理调和 | 词元相似度与对立标记冲突识别，1~3 遍调和；注入器使用 | ✅ |
| `dialectic_engine.py` | 推理调和 | 关键词对冲突识别与调和；包以 `MultiPassDialecticReconciler` 之名导出，供辩证 API 使用 | ✅ |
| `__init__.py` | 包门面 | 统一导出注入器、调和引擎与模型 | — |
