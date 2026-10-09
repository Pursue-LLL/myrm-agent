# CJK Iteration Mark Service Architecture (_ARCH.md)

## 1. 模块定位
本模块是业务后端服务层中负责与底座 Harness 引擎 `cjk_iteration_mark` 对接的业务适配器，提供 CJK 叠字「々」消歧、三维 Token 矩阵合成与双向召回匹配计算能力。

## 2. 核心职责
- 将 Pydantic V2 DTO 与 Harness 领域实体进行强类型、无损互转（严禁 `typing.Any`）；
- 封装文本消歧展开与召回重合度评分；
- 为 REST 路由层提供轻量、单例的高性能业务门面。

## 3. 依赖规则
- 允许依赖：`myrm_agent_harness.toolkits.memory.cjk_iteration_mark.*` 与 `app.schemas.cjk_iteration.*`；
- 禁止依赖：其他非相关业务模块；严格单向依赖，禁止反向耦合。
