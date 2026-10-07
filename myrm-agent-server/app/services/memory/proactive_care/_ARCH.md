# Proactive Care & Schedule Rebalancing Server Service Contract

## 1. 业务层职责与边界
- **职责**：
  - 维护 `ProactiveCareRebalancingService` 单机单例生命周期与依赖注入；
  - 暴露端点供 Web UI 与移动健康客户端同步体征指标、记录疲劳线索、查询活力状态、重平衡排期与拉取关怀通知；
  - 保持单机轻量无状态/单用户沙箱模式，严禁引入多租户数据混杂。
- **架构约束**：
  - 必须仅从 `myrm_agent_harness.toolkits.memory` 顶层统一导入所需符号；
  - 单文件严格 <400 行，无 `Any` 类型，严格使用三行分形文档头。
