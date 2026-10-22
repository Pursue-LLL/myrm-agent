# Live Remote Desktop Streaming & Ephemeral Shareable Canvas Suite (`remote-desktop/live-stream`)

## 1. 架构定位与业务痛点
针对长程复杂 GUI 与自动化网页浏览（CUA / Web Browsing）任务执行期间，用户只能面对纯文本旋转加载圈（Spinner）或干瘪日志，对沙箱内部到底是在正常操作还是卡死/死循环完全黑盒，产生极强不信任感的痛点，本模块对标火山方舟 Agent Plan 专属 Harness 工具「Agent 云电脑」，提供内嵌沙箱远程桌面实时视窗、解耦断网续看、免密时效安全分享链接与双向人工接管套件。

## 2. 模块拓扑与职责划分
- **`remoteDesktopTypes.ts`**：强类型契约定义连接状态 `StreamConnectionState`、控制模式 `ControlMode`、流媒体质量遥测指标 `StreamQualityMetrics`（FPS、延迟 RTT、码率、分辨率）、桌面动作日志 `DesktopActionTelemetry` 与时效凭据 `EphemeralShareTicket`；
- **`ephemeralTokenSecurity.ts`**：时效安全签名纯函数引擎，处理凭证生成 `generateEphemeralShareTicket`、确定性签名校验 `verifyEphemeralShareTicket` 与剩余时间格式化 `formatTimeRemaining`；
- **`useRemoteDesktopStore.ts`**：Zustand 集中式状态总线，管理 WebRTC 流推拉状态、双向控制权接管状态机、时效签名生成与事件派发，支持 `myrm:remote-desktop-takeover-changed` 与 `myrm:ephemeral-share-created` 全局事件；
- **`LiveDesktopCanvasViewport.tsx`**：内嵌沙箱远程桌面实时视窗组件，自适应推流帧率（静止 1fps，操作 30fps）、呈现 Agent 虚拟鼠标坐标与近期动作滚动条；
- **`HumanTakeoverControlOverlay.tsx`**：双向人工接管浮动控制条，在需要人工输入验证码或高危操作时发出警报，支持一键锁定控制权与无损交还 Agent；
- **`EphemeralShareModal.tsx`**：采用 HTML5 原生 `<dialog open>`，提供 TTL 时长选择（1h/2h/24h）、双向接管授权与一次性销毁凭据配置，一键复制免登录专属分享链接。

## 3. 极不友好 Code Review 12 项清单遵循度
1. **零 Any**：全强类型 TypeScript 标注；
2. **零原生 Emoji**：全部采用 Lucide 矢量图标（Monitor, Play, Pause, RefreshCw, Share2, Key, ShieldCheck, AlertTriangle, Maximize2, Minimize2, Wifi, MousePointer 等）；
3. **前端所有 If 显式带大括号**：严格杜绝无括号写法；
4. **单文件行数严格受控**：各文件行数受控在 260 行以内（远低于 400 行红线）；
5. **a11y 无障碍标准**：采用 HTML5 原生 `<dialog open>` 模态框，遮罩层与内容分离，按钮均具备明确 `aria-label` 与 `type="button"`。
