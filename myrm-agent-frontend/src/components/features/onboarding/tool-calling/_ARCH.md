# tool-calling/ 模块架构

## 架构概述

为首次启动向导（`LocalCapabilitiesSetup`）与模型配置面板提供**实测工具调用推荐模型清单**与**能力防呆匹配校验**。
杜绝新用户误选不支持 Function/Tool Calling 的模型，避免 Agent 工具调用静默失败。

## 文件清单

| 文件 | 职责 |
| ---- | ---- |
| `verifiedToolModels.ts` | 实测验证的 Tool Calling 模型 SSOT 清单（Claude 3.5 Sonnet, GPT-4o, DeepSeek-V3, Qwen 2.5 Coder 32B 等）及正则/模糊匹配判定函数 |
| `ToolCallingModelChecklist.tsx` | 推荐模型 Checklist 交互组件，支持快速点击选取预设模型、高亮当前选中项及多语言国际化 |

## 依赖

- `@/components/features/onboarding/LocalCapabilitiesSetup.tsx`
- `lucide-react`
- `next-intl`
