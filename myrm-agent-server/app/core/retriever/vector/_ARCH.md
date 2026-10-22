# vector 模块架构

## 架构概述

业务层向量存储入口。核心实现（VectorStore ABC、Qdrant 实现、配置模型）位于框架层 `myrm_agent_harness.toolkits.vector`，本模块负责：
1. **重新导出** 框架层的向量存储 API（含远程模式实例池 `VectorStorePool`）
2. **业务默认配置** (defaults.py) — 基于 QDRANT_PATH 环境变量的嵌入式 Qdrant 配置

**所有部署模式（Local / Sandbox）统一使用 Qdrant 嵌入式模式。** Sandbox 模式下 Qdrant 运行在用户云电脑内，数据存储在云电脑持久化卷上。

---

## 设计决策：为什么选择嵌入式 Qdrant 而非控制平面共享集群

Agent-in-Sandbox 架构下，每个用户拥有独立云电脑实例。向量数据库嵌入云电脑内，而非部署在控制平面共享：

| 维度 | 云电脑内嵌入式（当前方案） | 控制平面共享集群 |
|------|------------------------|----------------|
| 隔离性 | 物理隔离，数据不可能跨用户泄露 | 逻辑隔离（tenant_id），存在 bug 打穿风险 |
| 代码统一性 | 本地与 Sandbox 完全同一套代码 | 需要两套路径（嵌入式 + 远程 SDK） |
| 运维成本 | 零（随云电脑自动创建/销毁） | 需独立集群的高可用、备份、扩容 |
| 故障隔离 | 仅影响单用户 | 集群故障影响所有用户 |
| 架构一致性 | 符合框架三不原则（不感知多租户/部署模式） | 框架需感知 tenant_id，违背三不原则 |

**资源消耗**（单用户典型场景，1536 维向量）：

| 向量数量 | 内存占用 |
|---------|---------|
| 100（轻度） | ~1 MB |
| 1,000（中度） | ~9 MB |
| 10,000（重度） | ~88 MB |

嵌入式 Qdrant 是进程内库（pip 依赖），无独立进程、无端口占用。云电脑休眠时内存随进程释放。

**竞品参考**：2026 主流 Personal Agent 云电脑普遍不使用共享向量数据库，记忆以 file-based 形式存储在各自云电脑内。我们的嵌入式 Qdrant 在保持相同的物理隔离特性的同时，多了语义向量检索能力。

**2026 行业趋势验证**：
- [RisingWave](https://risingwave.com/blog/stateful-sandboxes-for-ai-agents)："Stateful sandboxes require persistent embedded databases within the sandbox itself"
- [PingCAP](https://www.pingcap.com/blog/local-first-rag-using-sqlite-ai-agent-memory-openclaw/)：2026 趋势是 local-first + zero-ops 嵌入式数据库配合 OS 级沙箱
- [Zylos Research](https://zylos.ai/research/2026-03-09-multi-agent-memory-architectures-shared-isolated-hierarchical)：隔离式嵌入式数据库可防止噪音污染和跨用户数据泄露
- [Fly.io: Code And Let Live](https://fly.io/blog/code-and-let-live)（Annie Ruygt）：Sprites 提供持久化 Firecracker microVM（100GB ext4 + Checkpoint/Restore），验证「云电脑 + 嵌入式数据库」是 Agent 基础设施主流方向

---

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 从框架层重新导出向量存储 API + 业务默认配置 | ✅ |
| `defaults.py` | 业务 | 基于 QDRANT_PATH 的嵌入式默认配置；不触碰数据目录锁——单写者由框架层 OS 文件锁保证，第二个进程被拒后回退内存模式，工厂置位 `system_status.vector_degraded`（`/health` 输出，Web UI 向所有用户常驻提示）并由记忆指挥中心展示 | ✅ |
**框架层实现** (`myrm_agent_harness.toolkits.vector`)：
- `toolkits/vector/base.py` — VectorStore ABC + 数据模型
- `toolkits/vector/config.py` — 部署模式 + 配置
- `toolkits/vector/qdrant/store.py` — QdrantVectorStore 实现
- `toolkits/vector/qdrant/factory.py` — 工厂函数 + Singleton 管理
- `toolkits/vector/qdrant/filters.py` — 过滤器构建

---

## 依赖关系

### 外部依赖
- `myrm_agent_harness.toolkits.vector` — 向量存储抽象和 Qdrant 实现

### 被依赖
- `app/core/memory/adapters/` — 记忆系统适配器
- `app/api/health/router.py` — 就绪检查
