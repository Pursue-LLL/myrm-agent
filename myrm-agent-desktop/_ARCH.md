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
| `src-tauri/` | Rust 主程序、IPC、托盘、更新校验 → [ARCHITECTURE.md](ARCHITECTURE.md) |
| `src-tauri/frontend-shell/` | Release 模式 WebView 占位页：`withGlobalTauri` 启用后 IPC 读取 `webui_port`，轮询 Next standalone 就绪并跳转 |
| `sidecar/` | PyInstaller + agent-runner 编译入口 |
| `scripts/` | 桌面构建/签名辅助 → [scripts/_ARCH.md](scripts/_ARCH.md) |

## Windows 打包

- NSIS `installerIcon` 使用 `icons/icon.ico`（NSIS 不接受 PNG）
- 多语言安装器：English / 简中 / 繁中 / 日 / 韩 / 德

## OTA 与发版清单

- `tauri.conf.json#plugins.updater.pubkey`：占位符时 `updater_safety.rs` 禁用生产 OTA；真实公钥 + CI `TAURI_SIGNING_PRIVATE_KEY` 配对后启用
- `finalize-release.sh` 将各平台 `.sig` 写入 `latest.json#platforms.*.signature`，与 `useAppUpdate.ts` 状态机共用同一 manifest
- `verify-release.sh`：finalize 后断言 `latest.json` 版本/OTA signature 与安装包 `.sha256` sidecar
- CI：`build-windows` 上传 `MyrmAgent_x64-setup.exe` + `.sig`（Tauri v2 Windows OTA 资产；`*.nsis.zip` 为 bundling 临时文件）；完成后 `finalize-release`；`build-linux` 完成后 `refinalize-after-linux`（不阻塞主路径）
- CI 构建前 `check-updater-pubkey.sh`：私钥已配但 pubkey 仍占位 → fail；仅占位 → warning，安装包照常发布

## 依赖

- 内嵌/伴随 `myrm-agent-server`、`myrm-agent-frontend` 静态资源
- **不**依赖 PyPI harness 打包进 Tauri（后端 sidecar 已捆绑解释器/runtime）
- 发版 CI：`scripts/ci/desktop-release/` · [../scripts/ci/desktop-release/_ARCH.md](../scripts/ci/desktop-release/_ARCH.md)

## 文档

- L1 架构：[ARCHITECTURE.md](ARCHITECTURE.md)
- 发版签名：[DESKTOP_RELEASE_SYSTEM.md](DESKTOP_RELEASE_SYSTEM.md)
- 用户向快速入门：[README.md](README.md)（安装与 Releases）
- Rust 模块清单：[src-tauri/src/_ARCH.md](src-tauri/src/_ARCH.md)
- 分形文档门禁：`scripts/check-fractal-docs.ts`（CI：`desktop-fractal-docs.yml`）
