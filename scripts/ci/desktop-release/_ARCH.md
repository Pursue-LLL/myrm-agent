# desktop-release CI 脚本

## 架构概述

桌面 GitHub Release 流水线辅助脚本；由 `.github/workflows/desktop-release.yml` 按 job 调用。

## 文件清单

| 文件 | 职责 |
|------|------|
| `inject-version.sh` | tag → `myrm-agent-desktop/src-tauri/tauri.conf.json` 版本 |
| `sync-server-venv.sh` | 生产 sidecar venv（`--no-group dev`）；GHA+`MYRM_HARNESS_INSTALL_MODE=pypi` 时走 PyPI.org（规避 lock 内清华镜像 403） |
| `finalize-release.sh` | 下载 Release 资产（与 API 计数对齐重试）→ 匹配 updater 包 + `.sig` → `latest.json` + `.sha256` → upload |
| `pick-platform-asset.sh` | OTA 平台资产匹配（`finalize-release.sh` / fixture 共用；glob 加引号 + nullglob） |
| `bundle-paths.sh` | `is_release_bundle_path` / `is_updater_bundle_path`（Windows 反斜路径兼容） |
| `rename-updater-bundles.sh` | Intel：`MyrmAgent_x64.app.tar.gz`（macOS bash） |
| `rename-windows-updater-bundle.ps1` | Win：`MyrmAgent_x64-setup.exe`（GHA pwsh；Tauri v2 OTA 用 setup.exe，nsis.zip 为临时文件） |
| `verify-release.sh` | finalize 后 smoke：`latest.json` 版本/OTA signature + 安装包 `.sha256`；`REQUIRE_MIN_OTA_PLATFORMS` + `REQUIRED_OTA_PLATFORM_KEYS` 分阶段门禁 |
| `check-updater-pubkey.sh` | 构建前校验 pubkey 与 `TAURI_SIGNING_PRIVATE_KEY` 一致性；占位符仅 warning |
| `sign-updater-bundles.sh` | 构建后补签 updater 包；Mac ARM 设 `REQUIRE_UPDATER_BUNDLES=1`；用 `bundle-paths` 过滤 |
| `finalize-fixture-test.sh` | 无网络 fixture：四平台匹配 + `.sig`；`tests/architecture/test_desktop_finalize_fixture.py` 门禁 |
| `collect-bundle-assets.sh` | `find` + `bundle-paths` 收集 release/bundle 资产供 `gh release upload` |
| `prune-frontend-linuxmusl.sh` | Linux AppImage 前剔除 standalone 内 `@img/sharp-linuxmusl-*` 等，避免 linuxdeploy 缺 `libc.musl-x86_64.so.1` |
| `linux-appimage-sidecar-workaround.sh` | dummy-swap（tauri#11898）：bundling 用 gcc stub，打包后换回 Bun/PyInstaller 真 sidecar 并 repack |
| `bundle-find.sh` | GHA Windows 强制 `/usr/bin/find`（规避 System32/find.exe） |
| `.github/workflows/desktop-release-repair.yml` | `workflow_dispatch`：对已有 tag 重跑 finalize + verify（无需全平台 rebuild） |

## Workflow jobs

| Job | 职责 |
|-----|------|
| `prepare-frontend` | `bun run build:tauri` 一次，artifact 供 mac/win/linux 复用 |
| `build-macos-arm` | 主路径发 Release |
| `build-macos-x64` | macOS Intel (x86_64) 追加 dmg/tar.gz/.sig |
| `build-windows` | Windows 追加资产（finalize 门禁平台） |
| `build-linux` | Linux 仅 `--bundles appimage`（官网分发所需；不阻塞 finalize） |
| `finalize-release` | Mac+Win 完成后：`latest.json` + sha256 + verify |
| `refinalize-after-linux` | Linux 上传后重跑 finalize + verify |

**官网部署（brand 仓，非 agent CI）**：desktop `v*` Release 完成后，在 `myrm-agent-brand` 打 `website-v{semver}` tag → `website-release.yml` preflight bake + POST `CF_PAGES_DEPLOY_HOOK`；或本地 `bun run release:website -- website-v*`。

`collect-bundle-assets.sh`：`bundle-find.sh` + `bundle-paths` 收集资产；Bash 3.2 兼容（macOS GHA 无 `mapfile`）；workflow upload 步亦用 `while read`。

## Secrets（myrm-agent 仓库）

| Secret | 用途 |
|--------|------|
| `TAURI_SIGNING_PRIVATE_KEY` | Tauri updater 包签名；与 `tauri.conf.json#plugins.updater.pubkey` 成对 |

## OTA manifest 匹配规则

`latest.json` 仅纳入 **updater 包**且存在配对 `.sig` 的平台：macOS `.app.tar.gz`、Windows `*-setup.exe`（上传前重命名为 `MyrmAgent_x64-setup.exe`）、Linux `.AppImage.tar.gz`。ARM 保留 `MyrmAgent.app.tar.gz`；Intel 重命名为 `MyrmAgent_x64.app.tar.gz`（避免 `--clobber` 覆盖 ARM OTA）。Tauri v2 的 `*.nsis.zip` 为 bundling 临时文件，不可作 OTA 资产。`pick-platform-asset.sh` 的 glob 必须加引号。不含裸 `.msi` / `.deb` / 裸 `.AppImage` 候选。Linux job：`prune-frontend-linuxmusl.sh` + `linux-appimage-sidecar-workaround.sh` + `NO_STRIP=true` + `libfuse2` + `APPIMAGE_EXTRACT_AND_RUN=true` + `--bundles appimage`。

| `APPLE_*` / `KEYCHAIN_PASSWORD` | 可选；未配置时 Mac job 不传 env，避免空证书触发 codesign 失败；OTA 仍靠 minisign |

## 依赖

- 父模块 [../_ARCH.md](../_ARCH.md)
- 营销站发布契约：`myrm-agent-brand/myrm-website/scripts/release-website.ts` (POS: tag + Deploy Hook 手动发布入口)
