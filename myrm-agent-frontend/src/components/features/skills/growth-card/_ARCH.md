# components/features/skills/growth-card 模块架构

## 架构概述

技能进化提案卡片（`SkillGrowthCaseCard`）的子区块。父卡片持有展开/修订/审批状态与数据加载，这里的组件只负责展示与就地修订编辑，扫描相关文案统一经 `useScanRiskText` 本地化，不向用户暴露内部类别码或信号码。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `GrowthCaseTitleRow.tsx` | 组件 | 标题行：提案类型、状态、来源、验证与安全徽章（信任等级走封闭词表，词表外不着色） | ✅ |
| `GrowthCaseEvidence.tsx` | 组件 | 证据区：验证证明、安全扫描发现（类别/严重度本地化）、运行时失败、待审原因（风险信号 + 处置建议）、应用失败 | ✅ |
| `GrowthRevisionEditor.tsx` | 组件 | 提案就地修订面板：Monaco DiffEditor + 取消/保存，内容与提交由父卡片持有 | ✅ |

## 设计原则

- **展示与状态分离**：子区块无自有业务状态，父卡片传入 `item` 与回调。
- **扫描文案单一出口**：类别码、严重度、风险信号与处置建议全部经 `useScanRiskText`，词表之外显示通用文案。
- **零原生 emoji**：图标统一采用 Lucide SVG 矢量图标。
