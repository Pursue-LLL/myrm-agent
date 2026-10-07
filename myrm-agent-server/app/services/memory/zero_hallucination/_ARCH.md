# Zero-Hallucination Memory Service Architecture

## 1. 模块定位
`app/services/memory/zero_hallucination` 属于业务服务层（`myrm-agent-server`），负责衔接底层 Harness 记忆评估契约（`MemoryStateAssertionEvaluator` 与 `ZeroHallucinationPromptGuard`）和前端/API 请求。

## 2. 核心职责
- **显式状态推断与映射**：将记忆搜索结果划分为 `FOUND`、`EXPLICIT_EMPTY`、`SERVICE_UNAVAILABLE`、`PARTIAL_DEGRADED` 4 种确定性状态，绝不默默返回空数组或吞掉异常。
- **抗衰减防伪提示词注入**：基于查询状态向 LLM 上下文注入双轨负向约束，明确禁止模型凭空捏造未配置的历史偏好。
- **子系统健康与降级监控**：监控向量库（Qdrant）、关系库（SQLite）与事实树（WorkingTree）各子系统的在线状态与延迟。

## 3. 依赖关系
- `myrm_agent_harness.toolkits.memory`: 底层强类型枚举与纯函数判定器
- `app.schemas.zero_hallucination`: Pydantic V2 请求与响应 DTO
