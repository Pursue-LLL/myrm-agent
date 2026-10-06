# plugins/

## 架构概述

Agent Plugins 1.0.0 的两条用户流程，共用同一份 ZIP 契约（harness `agent.plugins`，server `/plugins/*`）：

- **导入**：上传 ZIP → 组件级预览（技能安全扫描/超长/同名冲突、MCP、Agent、诊断；按部署形态标出本环境不可用的组件）→ 逐项决策 → 确认导入 → 结果页（逐 Agent 就绪度、未导入组件及原因、待补密钥）。
- **导出**：Agent 编辑面板发起 → 预览「将带出什么 / 需要补哪些密钥 / 没有带出什么」→ 共享脱敏复核（[`features/redaction/`](../redaction/_ARCH.md)）→ 下载 ZIP。

对话框只负责布局；流程状态在 hook，规则与类型在纯模块，便于单测。

## 文件清单

| 文件                                               | 地位 | 职责                                                                                                                                                                                                                                                           | I/O/P |
| -------------------------------------------------- | ---- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----- |
| `PluginImportDialog.tsx`                           | 核心 | 导入对话框布局壳：`!preview` 时显示 dropzone，预览态组合头部/技能/MCP/Agent 分区与可信来源门禁，确认后切到结果页（"再导入一个/完成"）；移动端全屏（`dialogLayout.ts`）                                                                                         | ✅    |
| `usePluginImportFlow.ts`                           | 核心 | 导入流程状态机：解析 → 预览 → 逐项决策 → confirm；错误文案经 `resolveUserFacingArchiveSecurityError` 按后端 `error_code` 稳定映射；confirm 成功后调用 `onImportComplete` 并强制刷新 Agent 列表，对话框保留结果页                                               | ✅    |
| `pluginImportTypes.ts`                             | 核心 | `/plugins/import/*` 线上类型（预览/确认/失败码）与纯规则：`isSkillBlocked`、`isServerBlocked`、`defaultDecisions`（被阻止或冲突项默认跳过）、`bulkResolution`（"全选"不会把被阻止项带回）                                                                      | ✅    |
| `PluginImportPreviewHeader.tsx`                    | 辅助 | 插件身份、风险与能力徽标（含权限升级提示）、部署形态提示（本环境不可装自定义技能 / 不可运行本地进程 MCP）、诊断                                                                                                                                                | ✅    |
| `PluginImportSections.tsx`                         | 辅助 | 技能 / MCP 分区：安全发现、超长、同名冲突（覆盖/跳过）、本环境不可用原因、能力等级徽标                                                                                                                                                                         | ✅    |
| `PluginImportAgentsSection.tsx`                    | 辅助 | Agent 分区：入口/子 Agent、将授予/留下的工具、解析不到的技能/MCP/子 Agent、循环上限被压低、作者模型仅提示；同名时「作为副本导入 / 覆盖 / 跳过」三选一，内置 Agent 不提供覆盖                                                                                   | ✅    |
| `PluginImportParts.tsx`                            | 辅助 | 分区外壳 `ImportSection`、两态开关 `ResolutionToggle`、说明行 `Note`、`listNames`                                                                                                                                                                              | ✅    |
| `PluginImportDropzone.tsx`                         | 辅助 | 语义化 label dropzone（拖拽/点击/键盘 Enter 均可选文件）与解析中状态                                                                                                                                                                                           | ✅    |
| `PluginImportResult.tsx`                           | 辅助 | 导入结果页：计数、逐 Agent 卡片（新建/覆盖、已保存上一版、留下的工具、就绪度）、失败项（本地化失败码，未知码回退通用句，绝不显示原始英文诊断）、待补密钥与 MCP 默认停用提示                                                                                    | ✅    |
| `useImportedAgentReadiness.ts`                     | 辅助 | 导入后按 Agent id 取一次就绪度（失败不阻塞结果页）                                                                                                                                                                                                             | ✅    |
| `PluginTrustedSourceDisclosure.tsx`                | 核心 | 可信来源与沙箱权限安全披露：Local 主机 OS 权限与 Cloud 独立 Volume 沙箱边界的诚实告示、提示词间接注入风险、受控 checkbox 门禁（未勾选禁用导入）                                                                                                                | ✅    |
| `ExpertExportDialog.tsx`                           | 核心 | 专家导出对话框：预览 → 复核 → 导出；有发现时上区为依赖闭包、下区为共享脱敏复核；"导出原文"仅在可构建且存在发现时出现，并对每条发现显式声明保留；预览后 Agent 被改动（`export_changed_since_preview`）→ 提示并重新预览；试构建失败（`build_error`）时不提供导出 | ✅    |
| `ExpertExportClosure.tsx`                          | 辅助 | 导出预览上区：Agent / 技能 / MCP（含需补密钥名）/ 工作区文件 / 未随包带出清单（本地化种类与原因码）                                                                                                                                                            | ✅    |
| `dialogLayout.ts`                                  | 辅助 | `MOBILE_FULLSCREEN_DIALOG`：窄屏全屏对话框覆盖类，导入/导出共用                                                                                                                                                                                                | ✅    |
| `PluginManagerDialog.tsx`                          | 核心 | 已导入插件管理：MCP server 状态徽标（enabled 绿点 / disabled 琥珀点 + 启用引导，`server_meta` 缺失时回退纯名称）、卸载确认；幂等刷新                                                                                                                           | ✅    |
| `__tests__/pluginImportTestKit.ts`                 | 测试 | 命名空间感知的 next-intl 桩与完整线上载荷构造器（`previewPayload`、`skillPreview`、`serverPreview`、`agentPreview`、`confirmResult`）                                                                                                                          | ✅    |
| `__tests__/PluginImportDialog.test.tsx`            | 测试 | 技能/MCP 流程：preview 渲染、blocked/冲突预选、replace 切换、全选/跳过、可信来源门禁、confirm 载荷、结果页、失败后保留预览                                                                                                                                     | ✅    |
| `__tests__/PluginImportAgents.test.tsx`            | 测试 | Agent 流程：分区渲染、逐项/批量跳过、同名三选一与内置不可覆盖、部署形态阻止原因、结果页（就绪度/失败码/待补密钥/刷新列表）、就绪度不可用降级                                                                                                                   | ✅    |
| `__tests__/ExpertExportDialog.test.tsx`            | 测试 | 导出：摘要回传、文件名回退、按所选保留发现导出脱敏版、导出原文的显式决定、预览后改动重新复核、拒绝/构建失败/预览失败                                                                                                                                           | ✅    |
| `__tests__/PluginTrustedSourceDisclosure.test.tsx` | 测试 | 披露卡片：Local/Cloud 分支、勾选回调、禁用态                                                                                                                                                                                                                   | ✅    |
| `__tests__/PluginManagerDialog.test.tsx`           | 测试 | server_meta 徽标渲染与回退、空态、列表加载失败 toast                                                                                                                                                                                                           | ✅    |

## 依赖

- `@/services/expertPackage`（导出契约）、`@/lib/api`（导入契约走 `apiRequest`）、`@/store/useAgentStore`（导入后刷新列表）、`@/services/agent`（就绪度）
- `@/components/agent/AgentReadinessList`、`@/components/features/redaction/*`
- `@/components/primitives/*`
- 父模块 [`features/_ARCH.md`](../_ARCH.md)
