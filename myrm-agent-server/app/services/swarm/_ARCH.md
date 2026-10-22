# services/swarm 架构说明

---

## 模块定位

`SwarmExecutionService` 承载多智能体蜂群并发协同（Swarm Mode）、显式规则与偏好记忆自动唤醒（Recalled Rules HUD）、以及交付物人类负责人待核实风险清单（Owner Action & Risk Checklist）的业务服务（Item 42 P0）。
接入底层 Harness 框架的 `SwarmCoordinationEngine`，提供会话级蜂群配置管理、子 Agent 专属任务边界跟踪、上一轮记忆与业务规则显式召回登记与微调禁用、以及方案尾部店主/负责人核查风险项的确权管理。

---

## 文件清单

| 文件 | 地位 | 职责 |
|------|------|------|
| `service.py` | 核心 | 单例 `SwarmExecutionService`，封装蜂群状态切换、任务分发、记忆规则召回管理与方案风险项确权 |
| `__init__.py` | 门面 | 聚合导出 `SwarmExecutionService` |
| `_ARCH.md` | 文档 | 模块定位与架构索引规范 |

---

## 依赖关系

- `myrm_agent_harness.toolkits.swarm`
