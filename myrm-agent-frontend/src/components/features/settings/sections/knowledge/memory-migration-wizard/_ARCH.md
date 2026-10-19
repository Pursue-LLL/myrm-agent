# memory-migration-wizard/

## 架构概述

外部助手记忆迁移 Wizard 的步骤 UI（`MigrationWizardSection.tsx` 负责状态与接口编排，本目录只负责呈现与步骤内交互）。目录名带 `memory-` 前缀是为了与 onboarding 的 `settings/sections/system/migration-wizard/`（竞品足迹扫描抽屉）区分开。

按「步骤 + 卡片」分层：步骤文件持有交互，卡片文件只吃 props 呈现；`wizardShared.ts` 收敛翻译契约与文案键表，避免各步骤各自维护一份。预览页条目较多：解析样例与指令预览默认折叠并带数量徽标，映射表、MCP 预览与 cron 跳过清单默认展开，计数、覆盖矩阵、泳道、告警、备份与确认保持常显。

## 文件清单

| 文件                     | 角色 | 职责                                                                                                                                                    | I/O/P |
| ------------------------ | ---- | ------------------------------------------------------------------------------------------------------------------------------------------------------- | ----- |
| `wizardShared.ts`        | 辅助 | `TranslationFn` 翻译契约、`resolveSourceDisplayName`（粘贴通道来源名）、`formatCronSkippedReason`（未知原因回退通用文案）、覆盖标签与 cron 跳过原因键表 | ✅    |
| `ScanStep.tsx`           | 核心 | 第一步：发现来源列表、目标 Agent 选择、OpenClaw 情景记忆开关、无来源空态；组装来源卡片、ZIP 上传与粘贴通道                                              | ✅    |
| `SourceLanes.tsx`        | 组件 | 来源卡片（置信度与资产计数）、云端 ZIP 上传区（拖拽 + 文件选择）、粘贴导入通道（导出提示词复制、体积提示、「用模型帮我整理」开关与预览按钮）            | ✅    |
| `PreviewStep.tsx`        | 核心 | 第二步：计数摘要、覆盖矩阵、泳道、告警、迁移前备份导出、历史会话导入开关（默认开）、密钥导入与技能可信来源确认，以及决定是否放行确认导入的门禁          | ✅    |
| `PreviewCards.tsx`       | 组件 | 常显卡片：覆盖矩阵、泳道矩阵（详情按服务端 `detail_parts` 本地化，未知码回退原始行）、会话预览、Hermes 架构映射、token 经济对比、摘要单元               | ✅    |
| `PreviewPanels.tsx`      | 组件 | 可折叠的参考性面板：解析样例、映射表、MCP 服务器预览、指令预览、cron 跳过清单（均由自身决定空态与徽标）                                                 | ✅    |
| `CollapsibleSection.tsx` | 组件 | 原生 `<details>/<summary>` 折叠壳（标题 + 数量徽标 + 箭头旋转），供预览面板复用                                                                         | ✅    |
| `ResultStep.tsx`         | 核心 | 第三步：导入结果计数、readiness 复查与就绪锚点、一键开启历史会话搜索、验证记忆入口、后续动作链接与回滚                                                  | ✅    |

## 依赖边界

- 只依赖 `@/services/*`、`@/lib/*`、`@/store/*` 与 `@/components/primitives/*`；不反向依赖 Settings 容器。
- 跨步骤共用的兄弟模块按相对路径直连（`../MigrationWizardReadiness`、`../MigrationVaultBindPanel`、`../CodexWikiCompletionLane`），不设 index.ts 桶文件。
