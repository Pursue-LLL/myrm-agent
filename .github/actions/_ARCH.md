# .github/actions 模块架构

## 架构概述

仓库内的本地 composite action：把多个 job 里逐字重复的步骤序列收成一处，调用方用 `uses: ./.github/actions/<名称>`（调用前必须先 `actions/checkout`，action 的代码就在仓库里）。

## 子目录

| 目录 | 职责 |
|------|------|
| `build-sidecar/` | 桌面四个平台构建 job 共用的“还原前端产物、装工具链、构建 PyInstaller sidecar”序列：下载 `frontend-tauri-build` 到 `myrm-agent-frontend/.next`，装 Bun / Rust / uv / Python 3.13，注入版本，把 `TARGET_ARCH` 导出到后续步骤，同步生产依赖 venv，运行 `sidecar/build.py`。输入 `arch`（必填：`arm64` 或 `x86_64`，构建结束时与产物架构对账）、`rust-target`（可选：macOS 构建非宿主三元组时要额外装的 Rust target） |

## 约束

- composite 里的 `run` 步骤必须写 `shell: bash`（Windows 的默认 shell 是 pwsh，而这些脚本是 bash）；`RELEASE_TAG` 来自调用 workflow 的 `env`
- 第三方 action 的钉 SHA 规则与 workflows 相同（见 [../workflows/_ARCH.md](../workflows/_ARCH.md)）
- 调用方与本 action 的约定由 `myrm-agent-server/tests/architecture/test_desktop_release_inputs.py` 钉住：每个构建 job 恰好调用一次且传入各自平台的架构、macOS 的 `rust-target` 与 Tauri 构建的 `--target` 一致、sidecar 只在这里构建、`TARGET_ARCH` 导出与 venv 同步先于 `build.py`

## 依赖

- [scripts/ci/desktop-release/_ARCH.md](../../scripts/ci/desktop-release/_ARCH.md) — `inject-version.sh`、`sync-server-venv.sh`
- [myrm-agent-desktop/sidecar/_ARCH.md](../../myrm-agent-desktop/sidecar/_ARCH.md) — `build.py`
- 父模块 [../_ARCH.md](../_ARCH.md)
