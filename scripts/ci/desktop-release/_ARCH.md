# desktop-release CI 脚本

## 架构概述

桌面 GitHub Release 流水线辅助脚本；由 `.github/workflows/desktop-release.yml` 按 job 调用。

## 文件清单

| 文件 | 职责 |
|------|------|
| `inject-version.sh` | tag → `myrm-agent-desktop/src-tauri/tauri.conf.json` 版本 |
| `sync-server-venv.sh` | 生产 sidecar venv（`--no-group dev`）：`uv sync --frozen` 装依赖（跳过 harness 本体）后，用仓库内 `myrm-agent-harness/` 构建 wheel 并安装（非 editable） |
| `finalize-release.sh` | 下载 Release 资产（与 API 计数对齐重试）→ 匹配 updater 包 + `.sig` → `latest.json` + `.sha256` → upload；`REQUIRED_OTA_PLATFORM_KEYS` 存在时缺 platform/.sig 硬失败 |
| `pick-platform-asset.sh` | OTA 平台资产匹配（`finalize-release.sh` / fixture 共用；glob 加引号 + nullglob） |
| `bundle-paths.sh` | `is_release_bundle_path` / `is_updater_bundle_path`：只认直接落在 `release/bundle/<kind>/` 的 Tauri 产物，`.app` / `.AppDir` 里的文件（sidecar 目录自带的归档等）一律不算，避免被补签或当 release 资产发布（Windows 反斜路径兼容；由 `test_desktop_bundle_outputs.py` 钉住） |
| `rename-windows-updater-bundle.ps1` | Win：`MyrmAgent_x64-setup.exe`（GHA pwsh；Tauri v2 OTA 用 setup.exe，nsis.zip 为临时文件） |
| `smoke-launch-runtime.ps1` | `build-windows` 在静默安装 NSIS 后的运行时烟测：按 `binaries/myrmagent-backend/` 目录布局校验 sidecar（非占位、含 `_internal/`），用全新数据目录拉起 Python sidecar（经 `Start-Process`，不继承本控制台的句柄——Tauri 壳是 GUI 进程，`--noconsole` 的 sidecar 因此没有标准流，继承句柄的启动方式会掩盖由此引起的崩溃）+ Next standalone，探测 `:8080/health` 与 `:webui_port`（与 Rust 壳相同的 120 s 预算），级联销毁进程树 |
| `verify-release.sh` | finalize 后 smoke：`latest.json` 版本/OTA signature + OTA 资产交叉校验 + 安装包 glob + 安装包 `.sha256`；`REQUIRE_MIN_OTA_PLATFORMS` + `REQUIRED_OTA_PLATFORM_KEYS` + `REQUIRED_INSTALLER_GLOBS` + `REQUIRE_BARE_LINUX_APPIMAGE` 分阶段门禁 |
| `smoke-launch-runtime.sh` | macOS（`.app` 与解压后的 updater tarball）和 Linux（AppImage 的 `squashfs-root`）的运行时烟测：`--bundle <目录>` 在其中定位唯一的 `binaries/myrmagent-backend/` 与 `frontend/` 里的 Next `server.js`（两者各自定位：AppImage 里 sidecar 目录树在 `usr/share/<product>`、前端在 `usr/lib/<product>`），校验入口非占位、可执行、`_internal/` 在位，用全新数据目录拉起 Python sidecar + Next standalone，探测 `:8080/health` 与 `:webui_port`；`--dev` 供维护者本地；`tests/architecture/test_desktop_launch_smoke_script.py`（语法）与 `test_desktop_sidecar_layout.py`（含真实启动的行为测试）门禁 |
| `export-apple-signing-env.sh` | 仅当 `APPLE_*` secret 非空时写入 `GITHUB_ENV`；已定义但为空的变量会让 bundler 尝试导入钥匙串而失败 |
| `check-updater-pubkey.sh` | 构建前校验 pubkey 与 `TAURI_SIGNING_PRIVATE_KEY` 一致性；占位符仅 warning |
| `sign-updater-bundles.sh` | 构建后补签 updater 包；Mac ARM 设 `REQUIRE_UPDATER_BUNDLES=1`；用 `bundle-paths` 过滤 |
| `finalize-fixture-test.sh` | 无网络 fixture：三个 OTA 平台的匹配 + `.sig`，旧 release 里的 Intel 包不被任何平台选中；`tests/architecture/test_desktop_finalize_fixture.py` 门禁 |
| `collect-bundle-assets.sh` | `find` + `bundle-paths` 收集 release/bundle 资产供 `gh release upload` |
| `prune-frontend-linuxmusl.sh` | Linux AppImage 前剔除 standalone 内 `@img/sharp-linuxmusl-*` 等，避免 linuxdeploy 缺 `libc.musl-x86_64.so.1` |
| `bundle-find.sh` | GHA Windows 强制 `/usr/bin/find`（规避 System32/find.exe） |
| `.github/workflows/desktop-release-repair.yml` | `workflow_dispatch`：对已有 tag 重跑 finalize + verify（无需全平台 rebuild） |

## Workflow jobs

| Job | 职责 |
|-----|------|
| `prepare-frontend` | `bun run build:tauri` 一次；artifact 带 `.next/standalone`（服务端，其编译产物在隐藏的 `.next/` 里，须 `include-hidden-files`）与 `.next/static`，三个构建 job 还原到 `myrm-agent-frontend/.next`，与 `tauri.conf.json` 的 `bundle.resources` 一一对应（`test_desktop_release_inputs.py` 钉住） |
| `build-macos-arm` | macOS 只发 Apple Silicon（Intel 为什么不发见 `DESKTOP_RELEASE_SYSTEM.md`）；主路径发 Release；构建后对 `.app` 与解压后的 updater tarball 各跑一次 `smoke-launch-runtime.sh`（解压出来的那份先设为只读：被 macOS 隔离运行的 `.app` 的目录不可写） |
| `build-windows` | Windows 追加资产（finalize 门禁平台）；静默安装 NSIS 后跑 `smoke-launch-runtime.ps1` |
| `build-linux` | Linux 仅 `--bundles appimage`（官网分发所需；不阻塞 finalize）；解出 AppImage 后设为只读（挂载的 AppImage 本来就不可写）再跑 `smoke-launch-runtime.sh`；sidecar 目录树在 AppImage 的 `usr/share/<product>/` 下（见 `tauri.linux.conf.json`） |
| `finalize-release` | Mac ARM + Win 完成后：`latest.json` + sha256 + verify；各道门（含 repair 工作流）要求的平台与构建 job 一致由 `test_desktop_release_gates.py` 钉住 |
| `refinalize-after-linux` | Linux 上传后重跑 finalize + verify |

三个构建 job 的前序（还原前端产物、装 Bun / Rust / uv / Python、注入版本、同步生产依赖 venv、构建 sidecar）是同一个 composite action `.github/actions/build-sidecar`，各 job 只传 `arch`（macOS 另传 `rust-target`）；其后才是各平台自己的步骤。契约测试 `tests/architecture/test_desktop_*.py` 由 `desktop-contracts.yml` 在这些文件改动时运行。

**验证运行**：非 tag 的 `workflow_dispatch` 会构建并烟测各平台包，但不创建 Release、不上传任何资产（所有上传步骤均 `if: github.ref_type == 'tag'`），版本为 `0.0.0-<run_number>`；`v*` tag push 才发布。

**官网部署（brand 仓，非 agent CI）**：desktop `v*` Release 完成后，在 `myrm-agent-brand` 打 `website-v{semver}` tag → `website-release.yml` preflight + GHA POST `CF_PAGES_DEPLOY_HOOK`；或本地 `bun run release:website -- website-v*`（preflight + push tag）。

`collect-bundle-assets.sh`：`bundle-find.sh` + `bundle-paths` 收集资产；Bash 3.2 兼容（macOS GHA 无 `mapfile`）；workflow upload 步亦用 `while read`。

## Secrets（myrm-agent 仓库）

| Secret | 用途 |
|--------|------|
| `TAURI_SIGNING_PRIVATE_KEY` | Tauri updater 包签名；与 `tauri.conf.json#plugins.updater.pubkey` 成对 |

## OTA manifest 匹配规则

`latest.json` 仅纳入 **updater 包**且存在配对 `.sig` 的平台：macOS `.app.tar.gz`、Windows `*-setup.exe`（上传前重命名为 `MyrmAgent_x64-setup.exe`）、Linux `.AppImage.tar.gz`。macOS 只有 Apple Silicon，包保留 Tauri 的 `MyrmAgent.app.tar.gz`；旧 release 里的 Intel 包 `MyrmAgent_x64.app.tar.gz` 不会被选作任何平台的更新。Tauri v2 的 `*.nsis.zip` 为 bundling 临时文件，不可作 OTA 资产。`pick-platform-asset.sh` 的 glob 必须加引号。不含裸 `.msi` / `.deb` / 裸 `.AppImage` 候选。Linux job：`prune-frontend-linuxmusl.sh` + `NO_STRIP=true` + `libfuse2` + `APPIMAGE_EXTRACT_AND_RUN=true` + `--bundles appimage`。

| `APPLE_*` / `KEYCHAIN_PASSWORD` | 可选；未配置时 Mac job 不传 env，避免空证书触发 codesign 失败；OTA 仍靠 minisign |

## 依赖

- 父模块 [../_ARCH.md](../_ARCH.md)
- 营销站发布契约：`myrm-agent-brand/myrm-website/scripts/release-website.ts` (POS: 本地应急 preflight + push tag)
