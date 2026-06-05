# settings/

## 架构概述

设置页框架与各 Section（模型、渠道、记忆、技能、Cron 等）。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `CommandEditor.tsx` | 组件/模块 | 见源码 | 见源码 |
| `CommandSettings.tsx` | 组件/模块 | 见源码 | 见源码 |
| `ConfigImportExport.tsx` | 组件/模块 | 见源码 | 见源码 |
| `ConfigTimeMachine.tsx` | 组件/模块 | 见源码 | 见源码 |
| `ConfigToggleItem.tsx` | 组件/模块 | 见源码 | 见源码 |
| `FormFields.tsx` | 组件/模块 | 见源码 | 见源码 |
| `ImportPreviewDialog.tsx` | 组件/模块 | 见源码 | 见源码 |
| `JsonEditor.tsx` | 组件/模块 | 见源码 | 见源码 |
| `LanguageSwitcher.tsx` | 组件/模块 | 见源码 | 见源码 |
| `MCPConfigForm.tsx` | 组件/模块 | 见源码 | 见源码 |
| `OptionSelect.tsx` | 组件/模块 | 见源码 | 见源码 |
| `SchemaForm.tsx` | 组件/模块 | 见源码 | 见源码 |
| `SearchServiceCard.tsx` | 组件/模块 | 见源码 | 见源码 |
| `SearchServiceEditDialog.tsx` | 组件/模块 | 见源码 | 见源码 |
| `SearxngInstallConsentDialog.tsx` | 组件/模块 | 见源码 | 见源码 |
| `SettingsIcons.tsx` | 组件/模块 | 见源码 | 见源码 |
| `SettingsLayout.tsx` | 组件/模块 | 见源码 | 见源码 |
| `SettingsMenu.tsx` | 组件/模块 | 见源码 | 见源码 |
| `SkinPicker.tsx` | 组件/模块 | 见源码 | 见源码 |
| `Switcher.tsx` | 组件/模块 | 见源码 | 见源码 |
| `Tooltip.tsx` | 组件/模块 | 见源码 | 见源码 |
| `common/` | 目录 | 子模块 | 见源码 |
| `default-model/` | 目录 | 子模块 | 见源码 |
| `mcp/` | 目录 | MCP 配置 UI（列表/编辑/导入/安全扫描 Ack） | 见 `mcp/_ARCH.md` |
| `mcp/MCPScanAckDialog.tsx` | 组件 | 高风险 MCP 配置确认对话框 | ✅ |
| `model-service/` | 目录 | 子模块 | 见源码 |
| `retrieval/` | 目录 | 子模块 | 见源码 |
| `sections/` | 目录 | 子模块（含 `GlobalSkillQualityDashboard`、`SkillQualitySection` 等活路径） | 见源码 |

## 依赖

- `@/store/*`、`@/services/*`、`@/components/primitives/*`
- 父模块 [`features/_ARCH.md`](../_ARCH.md)
