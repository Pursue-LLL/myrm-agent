# Interactive Web Terminal & Detachable PTY Session Suite 架构说明

## 1. 业务目标与核心价值
彻底破除桌面端 Agent 走向 Web 后终端沦为只读日志输出面板导致无法运行交互式 CLI/Vim/Top 命令以及页面刷新后台长任务被意外杀死的硬伤。
对标 Hermes PR #93508 核心承诺与工业级 Web Terminal 实践，实现：
1. **轻量高性能 ANSI 虚拟终端仿真 (Virtual Terminal Emulator)**：支持 VT100 / xterm 控制序列、ANSI 256 色/真彩色着色高保真渲染、光标回退、清屏与字符对齐；
2. **全键盘捕获与控制字符映射 (Full Keyboard & Signals)**：捕获 `Ctrl+C` (SIGINT)、`Ctrl+D` (EOF)、`Ctrl+Z` (SIGTSTP)、`Tab` 补全与方向键，支持交互式 REPL 与全屏工具；
3. **Detachable 持久化 PTY 会话流 (Detachable PTY Sessions)**：支持终端会话“脱钩 (Detach)”与“重新挂载 (Attach)”。用户刷新网页或切换标签页时，后台长任务进程在后台守护运行，重新连接后秒级回显历史屏幕缓冲区，绝不意外中断任务；
4. **多会话标签与移动端辅助键盘 (Multi-Session Tabs & Quick Keypad)**：支持多会话独立管理、一键新建、快速关闭与控制字符小键盘浮条。

## 2. 核心架构设计
- `webTerminalTypes.ts`: 纯粹强类型系统，零 `any`，严格规范 PTY 会话状态机、ANSI 样式片段、屏幕行缓冲区与键盘载荷；
- `webTerminalAnsiEmulator.ts`: 纯函数 ANSI 转义解析引擎、颜色代码映射表、按键控制序列转换器与行数受控缓冲区生成器；
- `useWebTerminalPtyStore.ts`: 基于 Zustand 的多 PTY 会话状态机，统一管理会话生命周期、Detached 脱钩/挂载调度、输入输出流与全屏切换；
- `InteractiveWebTerminalCard.tsx`: 现代化工业级交互卡片，集成多标签切换、ANSI 高保真渲染、闪烁光标、状态指示灯与快捷按键条。

## 3. 工程质量与安全红线守则
- **零 any 约束**：全量代码均使用严格强类型约束；
- **单文件行数受控**：各文件行数均严格控制在 350 行以内（远低于 400 行红线）；
- **零原生 emoji**：全部采用统一的 Lucide 矢量图标；
- **全括号与代码健壮性**：所有 `if` 均显式包裹 `{}`；
- **无障碍访问 a11y**：严格使用语义化 `<output>`、`<section>` 及关联 `<label>`。
