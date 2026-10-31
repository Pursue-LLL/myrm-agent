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
| `verify-release.sh` | finalize 后 smoke：`latest.json` 版本/OTA signature + OTA 资产交叉校验 + 安装包 glob + 安装包 `.sha256`；`REQUIRE_MIN_OTA_PLATFORMS` + `REQUIRED_OTA_PLATFORM_KEYS` + `REQUIRED_INSTALLER_GLOBS` + `REQUIRE_BARE_LINUX_APPIMAGE` 分阶段门禁 |
| `smoke_launch_shell.py` | 三个构建 job 在 `tauri-action` 之后对真实打包产物的整壳烟测：`--bundle <目录>`（macOS `.app` 或解压后的 updater 包、Windows 静默安装后的安装目录、Linux 的 AppImage `squashfs-root`）里的主程序以 Finder / 开始菜单启动时的工作目录与环境运行——工作目录在 macOS 是只读的 `/`、在 Windows 是安装目录（Linux 的 AppRun 自己切进镜像的只读 `usr`），PATH 里没有 Node.js，macOS 与 Linux 用全新的主目录（首次启动，最慢的一次）。要求壳自己拉起 Python 后端与随包 Node.js 起的 Next（`:8080/health` 与 `:13000`，180 s 预算，壳自己给后端 120 s、Next 45 s）、首页引用的 `/_next/static` 资源取得到、后端用随包数据构建的四个列表（技能、智能体模板、集成目录、搜索服务商）在全新主目录下非空（PyInstaller 只归档 Python，漏打的数据目录会让后端健康、列表却是空的；全新主目录下后端的第一次应答就带着这些数据，最多等 60 s 只是不让负载高的 runner 上一次偶发的慢请求或失败拖垮整轮）、就绪后稳定运行 5 s；最后让壳退出：Unix 发 SIGTERM，壳必须自己退出且它的所有子孙进程一并消失；Windows 没有 SIGTERM，不走优雅退出，杀进程树后两个端口必须无人再服务（逃出进程树的幸存者会占着端口）；任何一步失败都附上壳的日志尾部与进程表。只用标准库；门禁：`tests/architecture/test_desktop_launch_smoke_script.py`（启动环境、启动工作目录与工作流接线）与 `test_desktop_launch_smoke_run.py`（对替身 bundle 里真实子进程的行为测试，替身由 `tests/support/stand_in_shell_bundle.py` 生成）；随包数据本身由 `test_desktop_sidecar_data.py` 在构建前钉住 |
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
| `build-macos-arm` | macOS 只发 Apple Silicon（Intel 为什么不发见 `DESKTOP_RELEASE_SYSTEM.md`）；主路径发 Release；构建后对 `.app` 与解压后的 updater tarball 各跑一次 `smoke_launch_shell.py`（解压出来的那份先设为只读：被 macOS 隔离运行的 `.app` 的目录不可写） |
| `build-windows` | Windows 追加资产（finalize 门禁平台）；静默安装 NSIS 后对安装目录跑 `smoke_launch_shell.py` |
| `build-linux` | Linux 仅 `--bundles appimage`（官网分发所需；不阻塞 finalize）；解出 AppImage 后设为只读（挂载的 AppImage 本来就不可写），在虚拟 X 服务（`xvfb-run`）下跑 `smoke_launch_shell.py`（壳是 GUI 程序，没有显示就起不来）；sidecar 目录树在 AppImage 的 `usr/share/<product>/` 下（见 `tauri.linux.conf.json`） |
| `finalize-release` | Mac ARM + Win 完成后：`latest.json` + sha256 + verify；各道门（含 repair 工作流）要求的平台与构建 job 一致由 `test_desktop_release_gates.py` 钉住 |
| `refinalize-after-linux` | Linux 上传后重跑 finalize + verify |

三个构建 job 的前序（还原前端产物、装 Bun / Rust / uv / Python、注入版本、同步生产依赖 venv、构建 sidecar）是同一个 composite action `.github/actions/build-sidecar`，各 job 只传 `arch`（macOS 另传 `rust-target`）；其后各 job 用 `myrm-agent-desktop/scripts/fetch_node_runtime.py --target <三元组>` 取回随包 Node.js 运行时（`tauri.conf.json#bundle.externalBin` 的 `binaries/myrm-node`，Tauri 按目标三元组后缀找文件，缺了连 `cargo check` 都报错），再进入 `tauri-action` 与各平台自己的步骤。契约测试 `tests/architecture/test_desktop_*.py` 由 `desktop-contracts.yml` 在这些文件改动时运行。

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
