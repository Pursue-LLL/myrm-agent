# risk-approval 模块架构

## 架构概述

三级风险人机协同（HITL）确认卡片与 Dry-Run 预演交互组件库（Roadmap ⑨ Item 29）。
为高危破坏性操作提供物理刹车网关，消除 AI 静默执行危险动作的风险。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `riskApprovalTypes.ts` | 协议 | 三级风险级别（READ/WRITE/HIGH_RISK）、确认载荷与预演数据契约 | ✅ |
| `RiskConfirmationCard.tsx` | 组件 | 交互式高辨识度风险卡片：目标对象呈现、风险告警列表、参数 Diff/内联修改、Dry-Run 预演预览与确认/打回三态操作 | ✅ |
| `index.ts` | 门面 | 统一导出组件与类型接口 | ✅ |
| `RiskConfirmationCard.test.tsx` | 测试 | 风险级别自适应渲染、参数就地编辑、Dry-Run 触发与确认/打回回调测试套件 | ✅ |

## 契约要点

- **三级风险自适应主题**：
  - `Level 1 (READ)`：绿色/只读徽章，安全直接放行；
  - `Level 2 (WRITE)`：琥珀色徽章，参数摘要回显，支持 Dry-Run 预演模拟；
  - `Level 3 (HIGH_RISK)`：高危红色警示，强制挂起并要求 HITL 确认，校验单次有效授权令牌（`confirmation_token`）。
- **零 `any`、零原生 emoji**：全量采用语义化标签与 Lucide SVG 矢量图标。
- **单文件代码质量红线**：单个文件行数严格低于 400 行。
