# Dev Ports Listening Bar & Service Preview Hub

## 架构定位

开发端口智能监听条、进程管理与本地服务即时预览中枢（Dev Ports Listening Bar & Service Preview Hub · Item 14）为沙箱与全栈开发环境提供实时端口捕获、进程管控与安全隔离预览中枢。当本地或沙箱内启动 Vite (5173)、Next.js (3000)、FastAPI (8000) 等微服务时，系统自动感知并呈现于常驻 HUD 胶囊中，支持一键调出内嵌安全 iframe 预览、切换桌面/平板/手机视口、复制/生成公网穿透链接及终止释放端口进程。

## 模块清单

| 文件 | 职责 | 行数/规范 |
|---|---|---|
| `DevPortPreviewModal.tsx` | 即时预览抽屉/模态框：语义化 `<dialog>`，内嵌安全隔离 iframe，支持三重视口切换、刷新、公网穿透复制与一键终止进程 | `< 250` 行，零 `any`，Tailwind 响应式 |
| `DevPortsBar.tsx` | 常驻 HUD 端口监听胶囊：显示活跃端口总数与响应脉冲点，点击或按快捷键 `Cmd+Shift+P` 展开 Popover，消除 Dead Feature Path | `< 250` 行，零原生 emoji |
| `DevPortIndicator.tsx` | 实时就绪服务气泡胶囊：展示 `:3000 Listening` 脉冲徽标，支持从日志自动嗅探与一键拉起分屏预览 | `< 200` 行，零 `any`，零原生 emoji |
| `DevPortSplitPreviewer.tsx` | 嵌入式分屏 Web 实时预览抽屉：右侧分屏多视口（桌面/平板/手机）实时热重载、控制台日志与公网隧道穿透 | `< 350` 行，零 `any`，零原生 emoji |
| `index.ts` | 门面导出文件：统一导出预览模态框、监听条、就绪气泡与分屏预览器 | 统一入口 |
| `_ARCH.md` | 本模块架构说明与文件职责索引 | 遵循架构规范 |

## 核心特性

1. **自动探活与心跳轮询**：每 15 秒探活或基于 `devports:refresh` 自定义事件即时更新；
2. **多视口预览切换**：支持 100% 桌面、768px 平板与 375px 移动端精准响应式调试；
3. **安全隔离沙箱**：iframe 具备限定沙箱权限，防止父页面受不受信任代码劫持；
4. **一键穿透与管理**：支持一键生成临时公网安全隧道链接及快速终止僵尸/多余端口。
