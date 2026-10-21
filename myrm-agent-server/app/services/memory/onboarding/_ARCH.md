# Onboarding Insight Service Module

## 1. 模块定位与职责边界
本模块属于 `myrm-agent-server` 业务服务层中的记忆系统子模块（`app.services.memory.onboarding`）。
针对单机环境或沙箱实例内的用户会话，提供外部 AI Agent 历史会话探测、轻量采样调度、“初见报告”生成以及用户确认后的记忆原子持久化落地。

### 架构分工与依赖规范
- **Harness 框架执行引擎**：引用 `myrm_agent_harness.toolkits.memory` 顶层门面中的 `OnboardingSourceRegistry`, `MultiSourceOnboardingSampler`, `OnboardingInsightDistiller`, `OnboardingSampleOptions` 等核心引擎。
- **Server 业务层**：管理探测配置、报告会话生命周期、多智能体作用域分发（主智能体 / 专属智能体 / 全局共享记忆），并将结构化事实原子落盘。
- **架构红线**：严格禁止反向依赖；单文件严格 <400 行；所有函数签名与 DTO 强类型，严格零 `Any`。

## 2. 核心组件
- `service.py`：`OnboardingInsightService` 单例服务，提供 `scan_sources()`, `generate_report()`, `confirm_ingest()` 核心业务逻辑。
- `__init__.py`：导出 `OnboardingInsightService` 与全局单例获取器 `get_onboarding_insight_service()`。
