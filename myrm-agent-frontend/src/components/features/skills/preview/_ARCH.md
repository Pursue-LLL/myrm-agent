# components/features/skills/preview 模块架构

## 架构概述

外部浏览器真机无阻断预览组件包。彻底规避内置 iframe 沙箱因严格 Content-Security-Policy (CSP)、同源策略 (SOP) 及外部图片防盗链 (Referer 请求头) 导致的页面样式受限与裂图痛点，提供显式「用外部浏览器打开」通道。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `externalPreviewTypes.ts` | 核心 | 干净外部预览请求 Payload 与响应状态契约 | ✅ |
| `externalPreviewService.ts` | 核心 | 预览会话服务端注册与真实系统浏览器新 Tab 调度器 | ✅ |
| `ExternalBrowserButton.tsx` | 核心 | 显式触发按钮组件（状态反馈、图标过渡与工具提示） | ✅ |
| `index.ts` | 门面 | 统一导出公共组件与服务 | ✅ |

## 设计原则

- **真机通道优先**：利用服务端带 CSP 放行与 `no-referrer` 标头的隔离端点，确保在系统原生浏览器中 100% 忠实还原。
- **离线安全兜底**：在无网络或测试环境下，自动回退至嵌入 `<meta name="referrer" content="no-referrer">` 的 Blob 协议对象 URL。
- **零原生 emoji**：操作与反馈状态统一采用 Lucide SVG 矢量图标。
