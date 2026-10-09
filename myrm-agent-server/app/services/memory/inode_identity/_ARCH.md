# Inode Identity Service Architecture (_ARCH.md)

## 1. 模块定位
本模块是业务后端服务层中负责与底座 Harness 引擎 `inode_identity` 对接的业务适配器，提供工作区物理目录身份解析、重命名迁移识别及防重复同步（Double Sync）保障。

## 2. 核心职责
- 将 Pydantic V2 DTO 与 Harness 领域实体进行无损、强类型互转（严禁 `typing.Any`）；
- 封装物理 Inode 探测、符号链接穿透与原子重定向判定；
- 为 REST 路由层提供轻量、单例的高性能业务门面。

## 3. 依赖规则
- 允许依赖：`myrm_agent_harness.toolkits.memory.inode_identity.*` 与 `app.schemas.inode_identity.*`；
- 禁止依赖：其他非相关业务模块；严格单向依赖，禁止反向耦合。
