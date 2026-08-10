# plugins/

## 架构概述

Agent Plugins 1.0.0 插件导入向导 UI：上传 ZIP → 组件级预览（技能安全扫描/超长标记/同名冲突标记/诊断）→ 逐项决策 → 确认导入并绑定 Agent。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `PluginImportDialog.tsx` | 核心 | 插件导入对话框：ZIP 上传/拖拽、preview 组件列表（技能/MCP/诊断）、blocked（安全风险/超长）技能自动跳过、同名冲突技能默认跳过并支持"覆盖/跳过"决策（覆盖走 `replace` resolution）、Agent 绑定、confirm 落盘与结果 toast（含 `required_secret_keys` 密钥配置引导 + MCP 默认停用提示）；`resolveUserFacingArchiveSecurityError` 按后端 `error_code` 稳定映射错误文案 | ✅ |
| `__tests__/PluginImportDialog.test.tsx` | 测试 | 组件级回归：preview 渲染、安全风险/超长技能 blocked 与预选 skip、同名冲突技能预选 skip 与 replace 切换、全选/跳过、confirm 提交（含 replace resolution）与失败 toast | ✅ |

## 依赖

- `@/store/*`、`@/services/*`、`@/components/primitives/*`
- 父模块 [`features/_ARCH.md`](../_ARCH.md)
