# myrm-agent-desktop 模块架构

Tauri 桌面壳：托管 WebView（Next 静态导出）、系统 API、以及两类 Sidecar 二进制（Python 后端 + Bun Agent Runner）。

## Sidecar 对照表（避免命名混淆）

| 仓库路径 | 运行时角色 | 技术 | 默认端口 / 产物 | 管理者 |
|----------|------------|------|-----------------|--------|
| `sidecar/` | **Python 后端** Sidecar 构建脚本 | PyInstaller `build.py` | 打包到 `src-tauri/binaries/myrmagent-backend-*`；运行时 `PORT`（Desktop 常用 8080） | `sidecar/README.md` |
| `sidecar/agent-runner/` | **Agent Runner** 源码（CLI 工具可视化） | Bun → `bun build --compile` | `src-tauri/binaries/agent-runner-*` | 同上 `build.py` |
| `agent-sidecar/` | Agent Runner **开发时** TS 工程 | Bun / Node | 开发态 JSON-RPC，非生产路径名 | 与 `sidecar/agent-runner` 同源能力 |
| `src-tauri/src/sidecar/` | Rust **进程管理**模块 | Tauri | 拉起上述二进制、健康检查 | `src-tauri/src/_ARCH.md` |

**数据流（CLI 可视化）**: 用户输入 → Tauri IPC → Rust → Agent Runner 二进制 → 外部 CLI（claude/codex/gemini）→ 适配器 → WebView UI。

**与开源 server 关系**: Python Sidecar 入口为 `myrm-agent-server/app/main.py`（与本地 `myrm start` 同一应用，不同打包形态）。

## 子目录

| 目录 | 职责 |
|------|------|
| `src-tauri/` | Rust 主程序、IPC、托盘、更新校验 |
| `sidecar/` | PyInstaller + agent-runner 编译入口 |
| `agent-sidecar/` | Runner 开发依赖与 TS 源码 |
| `scripts/` | 桌面构建/签名辅助 |

## 依赖

- 内嵌/伴随 `myrm-agent-server`、`myrm-agent-frontend` 静态资源
- **不**依赖 PyPI harness 打包进 Tauri（后端 sidecar 已捆绑解释器/runtime）

## 文档

- 用户向长文仍见 [README.md](README.md)（安装与 Releases）
- Rust 模块清单：[src-tauri/src/_ARCH.md](src-tauri/src/_ARCH.md)
