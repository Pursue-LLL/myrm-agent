# Capacity HITL Candidate Management Server Service Contract

## 1. 业务层职责与边界
- **职责**：
  - 维护 `CapacityHitlService` 单机单例生命周期与依赖注入；
  - 暴露 REST API 端点供前端 Command Center / WebUI 查询容量预警状态、触发候选提议扫描、审查待办提案与提交决策；
  - 保持单机单用户沙箱无状态模式，严禁多租户数据混入。
- **架构约束**：
  - 必须仅从 `myrm_agent_harness.toolkits.memory` 顶层统一导入所需符号；
  - 单文件严格 <400 行，无 `Any` 类型，严格使用三行分形文档头。
