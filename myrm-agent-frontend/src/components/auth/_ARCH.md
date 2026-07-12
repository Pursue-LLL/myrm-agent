# auth/

## 架构概述

SaaS（`NEXT_PUBLIC_DEPLOY_MODE=sandbox`）与控制平面认证相关的 UI：分屏品牌区 + Google OAuth 登录。本机 WebUI 使用 `LocalLoginForm`（管理员密码，见 server `app/services/webui/`）。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
| ---- | ---- | ---- | ----- |
| `SandboxAuthLayout.tsx` | 核心 | SaaS 登录页分屏布局（品牌区 + 玻璃表单区） | ✅ |
| `SandboxLoginForm.tsx` | 核心 | CP Google OAuth 登录 | ✅ |
| `LocalLoginForm.tsx` | 核心 | 本机 WebUI 管理员密码表单 | ✅ |
| `OAuthButtons.tsx` | 核心 | 拉取 `GET /api/auth/config` 并跳转 OAuth authorize | ✅ |
| `oauth-provider-icons.tsx` | 辅助 | Google/GitHub 等 OAuth 提供商 SVG 图标 | ✅ |

## 路由

| 路径 | 组件 |
| ---- | ---- |
| `/auth/login` | `login/page.tsx` → sandbox: `SandboxAuthLayout` + `SandboxLoginForm`；local: `LocalLoginForm` |
| `/auth/register`、`/auth/verify-email` | `next.config.ts` 永久重定向至 `/auth/login` |

## Locale 接力

营销站 CTA 附 `?locale=en|zh`。App `middleware.ts` 首请求写 `NEXT_LOCALE` cookie 并 302 去掉 query。登录/OAuth 成功后 `lib/locale-personal-sync.ts` 将 cookie 同步至 `personalSettings.locale`，与 `messageRequest.ts` 优先级对齐。

## 依赖

- `@/lib/cp-base-url` — `resolveCpBaseUrl()` (POS: 控制平面 REST 基址)
- `@/lib/deploy-mode` — `isSandboxAuthBuild()` (POS: 部署模式判断)
- `@/store/useAuthStore` — CP JWT 会话 (POS: SaaS 前端认证状态)
