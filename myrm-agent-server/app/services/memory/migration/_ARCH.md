# Competitor Memory Migration Server Service Contract

## 1. 业务层职责与边界
- **职责**：
  - 维护 `CompetitorMigrationService` 单机单例生命周期与依赖注入；
  - 暴露端点供配置向导（Onboarding Wizard）和 WebUI 自动探测本地竞品资产、提交导入与查看历史迁移审计；
  - 保持单机轻量无状态/单沙箱模式，严禁引入多租户数据混入。
- **架构约束**：
  - 必须仅从 `myrm_agent_harness.toolkits.memory` 顶层统一导入所需符号；
  - 单文件严格 <400 行，无 `Any` 类型，严格使用三行分形文档头。
