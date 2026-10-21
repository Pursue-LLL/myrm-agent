# components/approval/

## 架构概述

工具审批（HITL）的 React UI 壳层：全局 Drawer 与多态审批卡片。决策逻辑、resume payload、visual 上下文在 `lib/approval/`；队列状态在 `@/store`。

## 文件清单

| 文件                              | 地位 | 职责                                                                                      |
| --------------------------------- | ---- | ----------------------------------------------------------------------------------------- |
| `ApprovalDrawer.tsx`              | 核心 | 全局审批抽屉（subagent 批量 decisions）；被风控拦下的理由让抽屉与卡片留着，不叠加失败提示 |
| `BatchHighRiskConfirmDialog.tsx`  | UI   | 批量审批高危破坏操作二次确认弹窗                                                          |
| `PolymorphicApprovalCard.tsx`     | 核心 | 单条审批卡片（shell/MCP/视觉/`knowledge_patch` 等形态）                             |
| `OutboundDraftApprovalBody.tsx`   | UI   | 渠道回复审核（`outbound_draft`）卡片主体：对方来信、待发回复及其附件、渠道/收件人         |
| `HighRiskEvidenceScreenshot.tsx`  | UI   | 高危 UI 动作证据截图卡（百分比定位红色圆圈标注目标，响应式、桌面/浏览器双通道）           |
| `CompactFileWriteApprovalRow.tsx` | UI   | Subagent 本地文件写 compact 行 + 折叠 Monaco 预览                                         |
| `SaveSkillApprovalPreview.tsx`    | UI   | save_skill / skill_manage save 审批 bundle 预览（#8）                                     |
| `MaskedCredentialInputCard.tsx`   | UI   | 敏感凭证安全掩码隔离提交卡片（单次票据徽章、短 TTL、投毒白名单校验、一键撤回）            |
| `ApprovalScopeNoteLine.tsx`       | UI   | `resolveScopeNote` 单行展示（Drawer / CLI 审批）                                          |
| `PtcHintBadges.tsx`               | UI   | MCP PTC read-only/destructive/open-world 注解 badge                                       |
| `__tests__/`                      | 测试 | 组件级测试                                                                                |

## 依赖

- `@/lib/approval/*` — 见 [lib/approval/_ARCH.md](../../lib/approval/_ARCH.md)
- `@/hooks/approval/useToolApprovalResolve.ts` 等
- `@/store` 审批队列

## 与 lib/approval 边界

- **本目录**：React 组件与交互
- **lib/approval**：纯函数、resume 构建、visual 解析
