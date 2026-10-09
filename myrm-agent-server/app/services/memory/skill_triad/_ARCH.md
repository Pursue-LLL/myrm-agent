# Memory Skill Triad & Scope Isolation Service Architecture (_ARCH.md)

## 1. 模块定位
本模块是业务后端服务层中负责与底座 Harness 引擎 `skill_triad` 对接的业务适配器，提供多租户物理 Scope 分区目录解析、Provider 可见降级状态观测、机器 CLI 信封格式化与集成流水线四步验证能力。

## 2. 核心职责
- 将 Pydantic V2 DTO 与 Harness 领域实体（`ScopeCoordinates`, `DegradedStateReport`, `MachineCliEnvelope`, `SurveyFinding`, `IntegrationSeams`）进行强类型、零 Any 互转；
- 封装物理 Scope 目录分配与原子清理；
- 为 REST 路由层提供轻量、单例的高性能业务门面。

## 3. 依赖规则
- 允许依赖：`myrm_agent_harness.toolkits.memory.skill_triad.*` 与 `app.schemas.skill_triad.*`；
- 禁止依赖：其他非相关业务模块；严格单向依赖，禁止反向耦合。
