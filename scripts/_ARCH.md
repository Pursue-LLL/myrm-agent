# scripts 模块架构

## 架构概述

OSS 安装与生命周期 CLI。`myrmagent.ai/install.sh` 与 `install.ps1` 经 Cloudflare Pages `public/_redirects` 307 指向本仓 `install-remote.*`，再执行 `install.*`。

## 文件清单

| 文件 | 平台 | 职责 |
|------|------|------|
| `install.sh` | Unix / Git Bash | 安装 uv、bun；`uv sync`；musl 下重装 platform core wheel；前端 build；注册 `myrm` |
| `install-remote.sh` | Unix | `curl \| bash` 入口：clone → `install.sh` |
| `install.ps1` | Windows | 同上（PowerShell 原生） |
| `install-remote.ps1` | Windows | `irm \| iex` 入口：clone → `install.ps1` |
| `myrm` | Unix | `setup` / `dev` / `start` / `stop` / `status`（curl `/api/v1/health` JSON）/ `update` / `doctor` / `searxng`；monorepo 下 `setup` 自动 editable harness，否则 PyPI |
| `dev/dev.sh` | Unix | `myrm dev`：仅后端 :8080 |
| `dev/start.sh` | Unix | `myrm start`：后端 :8080 + 前端 `bun run dev` :3000；LISTEN+冷编译 poll 30s；MCP>1 WARN |
| `myrm.ps1` | Windows | 同上；`start` 优先 `.venv\Scripts\python.exe` |
| `dev/setup.sh` / `setup.ps1` | 双平台 | clone 后首次：monorepo 自动 editable harness，否则 PyPI `uv sync`；`patchright install chromium` + `bun install` |
| `dev/run_server.sh` / `run_server.ps1` | 双平台 | 开发启动后端（与 `myrm start` 同策略） |
| `lib/resolve_agent_root.sh` | Unix | 嵌套目录与独立 clone 的根路径解析 |
| `lib/start_server.sh` | Unix | `run_server.sh` 用手动启动；日常用 `myrm dev` / `myrm start` |
| `dev/test-instinct-inbox-seed.py` | 双平台 | Instinct Inbox E2E：向运行中后端 POST seed-mock（或 `--direct` 直写 DB） |
| `dev/test-instinct-inbox-e2e.sh` | Unix | Instinct Inbox API pytest + seed-mock；UI 用 MCP chrome-devtools |
| `dev/_ARCH.md` | — | WebUI E2E 政策：MCP `--autoConnect` 主 Chrome；单 Agent tab；禁 `list_pages` 探活；`chrome-e2e-preflight.sh`；废弃 `browser-delegate-chrome-e2e.mjs` |
| `ci/install-pre-push-hook.sh` | Unix | 安装 pre-push 架构守门钩子 |

## Harness 代码生成（无 OSS 目录）

`generate_litellm_routing.py` 等生成器在闭源 `myrm-agent-harness` 维护者工具链运行；产物提交路径：`myrm-agent-frontend/src/store/config/litellmRouting.generated.ts`。勿在 OSS 复制生成器。

## 中国大陆网络自适应

`install.sh` / `install.ps1` 内置自动检测逻辑，无需用户手动配置：

1. **检测**：时区匹配 (Asia/Shanghai 等) + 探测 pypi.org 是否 3s 内可达
2. **切换**：自动设置 `UV_DEFAULT_INDEX`（清华 PyPI）、`BUN_CONFIG_REGISTRY`（npmmirror）、`PLAYWRIGHT_DOWNLOAD_HOST`（npmmirror）
3. **环境变量覆盖**：`MYRM_USE_CN_MIRROR=1` 强制启用 / `MYRM_NO_CN_MIRROR=1` 强制禁用 / 用户已设 `UV_DEFAULT_INDEX` 则不覆盖
4. **Docker**：`docker build --build-arg USE_CN_MIRROR=1` 启用 APT 阿里云 + PyPI 清华

## 约束

- 默认克隆到 `~/.myrm/myrm-agent`（Windows：`%USERPROFILE%\.myrm\myrm-agent`）
- 需预装 Git；Windows 原生扩展编译失败时以 `uv sync` 核心依赖为准（harness 已含 retrieval 等 extras）
- Harness：OSS `install.sh` 走 PyPI（`uv sync`）；monorepo 联调时 `dev/setup.sh` 检测旁路 `myrm-agent-harness` 并调用 `install_harness.sh` editable；musl Linux 下 `install.sh` 额外安装 `myrm-agent-harness-core-*-musl`；安装后执行 `assert_distribution_ready()`（失败时输出中英双语修复指引）
- Monorepo 下 `myrm dev` / `myrm start` 要求 venv harness 为 editable 源码（否则 exit 1）；PyPI 消费测试可设 `MYRM_SKIP_HARNESS_EDITABLE_CHECK=1`（本地/发布双链路见 `scripts/dev/MAINTAINER_QUICKSTART.md`）
- `MYRM_INSTALL_SKIP_FRONTEND=1`：CI 跳过后端以外步骤（见 `.github/workflows/install-smoke.yml`）
