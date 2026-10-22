# canvas/

## 架构概述

Canvas 画布文件严格沙箱隔离与交互式脚本动态鉴权体系（Item 44 P0）。
解决 Agent 生成富交互 Canvas、HTML 工件或外部导入画布文件时，潜在内嵌恶意 JavaScript 脚本访问宿主 `window.parent.localStorage` 窃取凭据或发起未授权跨站请求的安全隐患。
提供：
1. 严格沙箱 iframe 隔离容器（`sandbox="allow-scripts allow-forms"`，严禁 `allow-same-origin`）；
2. 严格 Content Security Policy (CSP) 元标签注入（默认禁止未知外发连接）；
3. 交互式外部网络外发与脚本执行鉴权门禁（Interactive Script & Network Egress Gate）；
4. 域名白名单记忆与安全审计日志追踪。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|---|---|---|---|
| `canvasSecurityTypes.ts` | 类型 | 领域类型定义：CanvasSandboxPolicy, CanvasEgressRequest, CanvasPermissionStatus, CanvasSecurityAuditEvent | ✅ |
| `useCanvasGatingStore.ts` | 状态 | Zustand 状态管理：白名单域名、挂起的外发请求队列、安全审计日志流转 | ✅ |
| `CanvasSecurityBridge.ts` | 核心 | CSP 策略注入器、防穿透安全垫片编译器、iframe postMessage 双向鉴权通信桥 | ✅ |
| `CanvasViewer.tsx` | 组件 | 严格沙箱化 Canvas 承载视窗、安全盾牌 HUD、交互式外发网络请求审批卡片 | ✅ |
| `index.ts` | 门面 | 统一对外导出公共组件、Hook、常量与领域类型 | ✅ |
