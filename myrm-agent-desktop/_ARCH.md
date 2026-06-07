# myrm-agent-desktop 模块架构

Tauri 桌面壳：托管 WebView（Next 静态导出）、系统 API、以及两类 Sidecar 二进制（Python 后端 + Bun Agent Runner）。

## Sidecar 对照表（避免命名混淆）

| 仓库路径 | 运行时角色 | 技术 | 默认端口 / 产物 | 管理者 |
|----------|------------|------|-----------------|--------|
| `sidecar/` | **Python 后端** Sidecar 构建脚本 | PyInstaller `build.py` | 打包到 `src-tauri/binaries/myrmagent-backend-*`；运行时 `PORT`（Desktop 常用 8080） | `sidecar/_ARCH.md` |
| `sidecar/agent-runner/` | **Agent Runner** 源码（CLI 工具可视化） | Bun → `bun build --compile` | `src-tauri/binaries/agent-runner-*` | `sidecar/build.py` |
| `src-tauri/src/sidecar/` | Rust **Agent Runner 进程管理** | Tauri | JSON-RPC stdio、事件转发 | `src-tauri/src/_ARCH.md` |
| `src-tauri/src/runtime/` | Rust **Python/Next.js Sidecar + Agent Runner 编排** | Tauri | 进程启动、Appshot、Setup Token | `src-tauri/src/_ARCH.md` |

**数据流（CLI 可视化）**: 用户输入 → Tauri IPC → Rust `sidecar/` → Agent Runner 二进制 → 外部 CLI（claude 等）→ JSON 事件 → WebView UI。

**与开源 server 关系**: Python Sidecar 入口为 `myrm-agent-server/app/main.py`（与本地 `myrm start` 同一应用，不同打包形态）。

## 子目录

| 目录 | 职责 |
|------|------|
| `src-tauri/` | Rust 主程序、IPC、托盘、更新校验 |
| `sidecar/` | PyInstaller + agent-runner 编译入口 |
| `scripts/` | 桌面构建/签名辅助 |

## 依赖

- 内嵌/伴随 `myrm-agent-server`、`myrm-agent-frontend` 静态资源
- **不**依赖 PyPI harness 打包进 Tauri（后端 sidecar 已捆绑解释器/runtime）

## 文档

- 用户向长文仍见 [README.md](README.md)（安装与 Releases）
- Rust 模块清单：[src-tauri/src/_ARCH.md](src-tauri/src/_ARCH.md)
