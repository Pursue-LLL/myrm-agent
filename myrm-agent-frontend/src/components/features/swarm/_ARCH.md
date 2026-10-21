# components/features/swarm 架构说明

---

## 模块定位

`swarm` 模块承载多智能体蜂群并发协同（Swarm Mode）、显式规则与偏好记忆自动唤醒（Recalled Rules HUD）、以及交付物人类负责人待核实风险清单（Owner Action & Risk Checklist）的前端状态机与核心组件（Item 42 P0）。
汲取 EvoX 桌面端极致交互体验：
1. **输入框一键「蜂群协同」快捷 Pill 切换器**（`SwarmModeToggle.tsx`）：快速切换多 Agent 平级并行；
2. **消息流顶部「记忆/规则自动唤醒」HUD 徽章**（`MemoryRecallBadgeHUD.tsx`）：直观呈现命中召回的规则，支持单条微调或临时停用；
3. **交付物尾部「待负责人确认的风险清单」折叠卡**（`OwnerActionRiskCard.tsx`）：结构化排查商业方案潜在外部风险，支持逐项 Check 确权闭环。

---

## 文件清单

| 文件 | 地位 | 职责 |
|------|------|------|
| `swarmTypes.ts` | 类型 | 领域模型与类型契约（SwarmModeConfig, SwarmSubagentTask, RecalledRuleItem, OwnerRiskItem），零 `any` |
| `useSwarmExecutionStore.ts` | 状态 | Zustand 状态管理，包含蜂群模式开关、子 Agent 任务流、召回规则列表与方案风险项确权状态 |
| `index.ts` | 门面 | 聚合导出模块符号 |
| `_ARCH.md` | 文档 | 模块定位与架构索引规范 |

---

## 依赖关系

- `zustand`（前端状态管理）
- `lucide-react`（纯 SVG 矢量图标）
- `next-intl`（双语国际化）
