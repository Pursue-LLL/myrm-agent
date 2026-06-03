# auth/

## 架构概述

SaaS（`NEXT_PUBLIC_DEPLOY_MODE=sandbox`）与控制平面认证相关的 UI：分屏品牌区 + Google OAuth 登录。本机 WebUI 使用 `LocalLoginForm`（管理员密码，见 server `app/services/webui/`）。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
| ---- | ---- | ---- | ----- |
| `SandboxAuthLayout.tsx` | 核心 | SaaS 登录/验证页分屏布局（品牌区 + 玻璃表单区） | — |
| `SandboxLoginForm.tsx` | 核心 | CP Google OAuth 登录（`OAuthButtons` oauthOnly） | ✅ |
| `LocalLoginForm.tsx` | 核心 | 本机 WebUI 管理员密码表单 | ✅ |
| `OAuthButtons.tsx` | 核心 | 拉取 `GET /api/auth/config` 并跳转 OAuth authorize | ✅ |
| `oauth-provider-icons.tsx` | 辅助 | OAuth 提供商图标 | — |

## 路由

| 路径 | 组件 |
| ---- | ---- |
| `/auth/login` | `login/page.tsx` → sandbox: `SandboxAuthLayout` + `SandboxLoginForm`；local: `LocalLoginForm` |
| `/auth/register` | 重定向至 `/auth/login`（同一 Google OAuth 建号） |
| `/auth/verify-email` | 遗留邮箱验证链接（CP API）；新部署以 Google 为主 |

## 依赖

- `@/lib/cp-base-url` — `resolveCpBaseUrl()` (POS: 控制平面 REST 基址)
- `@/lib/deploy-mode` — `isSandboxAuthBuild()` (POS: 部署模式判断)
- `@/store/useAuthStore` — CP JWT 会话 (POS: SaaS 前端认证状态)
