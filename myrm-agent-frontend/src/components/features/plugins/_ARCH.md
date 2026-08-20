# plugins/

## 架构概述

Agent Plugins 1.0.0 插件导入向导 UI：上传 ZIP → 组件级预览（技能安全扫描/超长标记/同名冲突标记/诊断）→ 逐项决策 → 确认导入并绑定 Agent。

## 文件清单

| 文件                                     | 地位 | 职责                                                                                                                                                                                                                                                                                                                                                                                                                             | I/O/P |
| ---------------------------------------- | ---- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----- |
| `PluginImportDialog.tsx`                 | 核心 | 插件导入对话框：语义化 label dropzone（拖拽/点击/键盘 Enter 均可选文件 + keyboardHint 引导）、preview 组件列表（技能/MCP/诊断）、blocked（安全风险/超长）技能自动跳过、同名冲突技能默认跳过并支持"覆盖/跳过"决策（覆盖走 `replace` resolution）、Agent 绑定、confirm 落盘与结果 toast（含 `required_secret_keys` 密钥配置引导 + MCP 默认停用提示）；`resolveUserFacingArchiveSecurityError` 按后端 `error_code` 稳定映射错误文案 | ✅    |
| `PluginManagerDialog.tsx`                | 核心 | 插件管理对话框：展示已导入插件及其 MCP server（name/enabled 状态徽标——enabled 绿点、disabled 琥珀点+「MCP 设置启用」引导 tooltip，`server_meta` 缺失时 fallback 纯 server 名）、卸载确认流程。幂等刷新，卸载成功后同步 server 层                                                                                                                                                                                                 | ✅    |
| `__tests__/PluginImportDialog.test.tsx`  | 测试 | 组件级回归：preview 渲染、安全风险/超长技能 blocked 与预选 skip、同名冲突技能预选 skip 与 replace 切换、全选/跳过、confirm 提交（含 replace resolution）与失败 toast                                                                                                                                                                                                                                                             | ✅    |
| `__tests__/PluginManagerDialog.test.tsx` | 测试 | 组件级回归：server_meta 状态徽标渲染、无 server_meta 时 fallback、空态、列表加载失败 toast                                                                                                                                                                                                                                                                                                                                       | ✅    |

## 依赖

- `@/store/*`、`@/services/*`、`@/components/primitives/*`
- 父模块 [`features/_ARCH.md`](../_ARCH.md)
