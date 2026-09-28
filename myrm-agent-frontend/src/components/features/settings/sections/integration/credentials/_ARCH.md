# settings/sections/integration/credentials 模块架构

## 架构概述

设置页「凭证」域：Vault 表单凭证、文件上传凭证、OAuth 集成连接。由 `credentials` Tab 路由 `CredentialsSection`。

## 文件清单

| 文件                        | 职责                                             |
| --------------------------- | ------------------------------------------------ |
| `CredentialsSection.tsx`    | 页面壳：聚合 Vault / 文件 / OAuth 子面板与对话框 |
| `useCredentialsSection.ts`  | 组合 storage + OAuth hooks                       |
| `useCredentialsStorage.ts`  | Vault / 文件凭证状态与 handlers                  |
| `useCredentialsOAuth.ts`    | OAuth 集成状态与 handlers                        |
| `credentialsError.ts`       | 错误 message 提取                                |
| `credentialsConstants.ts`   | OAuth 集成清单与轮询常量                         |
| `credentialsOAuthUtils.ts`  | OAuth 卡片状态与样式纯函数                       |
| `CredentialsVaultPanel.tsx` | Vault 凭证列表                                   |
| `CredentialsFilePanel.tsx`  | 文件凭证列表与缺失提示                           |
| `CredentialsOAuthPanel.tsx` | OAuth 集成卡片网格                               |
| `CredentialsDialogs.tsx`    | Vault/OAuth 模态框与删除确认                     |
| `SSHVaultPanel.tsx`         | SSH 主机凭证资产列表、连通性探测与只读门禁控制台 |
| `BreakGlassModal.tsx`       | 300s TTL 受保护变更窗口单次破窗紧急申请弹窗      |

## 依赖

- `@/services/credentials`
- `@/services/google-workspace-oauth`
- `@/services/xai-oauth`
- `@/services/memory/integration`
- `@/services/sshVault`
- 父模块 [integration/_ARCH.md](../_ARCH.md)
