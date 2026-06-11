# desktop-release CI 脚本

## 架构概述

桌面 GitHub Release 流水线辅助脚本；由 `.github/workflows/desktop-release.yml` 按 job 调用。

## 文件清单

| 文件 | 职责 |
|------|------|
| `inject-version.sh` | tag → `myrm-agent-desktop/src-tauri/tauri.conf.json` 版本 |
| `sync-server-venv.sh` | 生产 sidecar venv（`--no-group dev`） |
| `finalize-release.sh` | 下载 Release 资产（与 API 计数对齐重试）→ 匹配 updater 包 + `.sig` → `latest.json` + `.sha256` → upload |
| `verify-release.sh` | finalize 后 smoke：`latest.json` 版本/OTA signature + 安装包 `.sha256` sidecar 断言 |
| `check-updater-pubkey.sh` | 构建前校验 pubkey 与 `TAURI_SIGNING_PRIVATE_KEY` 一致性；占位符仅 warning |
| `sign-updater-bundles.sh` | 构建后补签 updater 包；Mac ARM 设 `REQUIRE_UPDATER_BUNDLES=1`；Win/Linux 无 updater zip 时 skip |
| `finalize-fixture-test.sh` | 无网络 fixture：平台匹配 + 无 `.sig` 跳过 OTA；`tests/architecture/test_desktop_finalize_fixture.py` 门禁 |
| `collect-bundle-assets.sh` | `find` 收集 `target/**/release/bundle/*` 资产供 `gh release upload` |
| `trigger-website-release.sh` | brand `main` 打 `website-v{semver}` tag + POST CF Pages Deploy Hook |

## Workflow jobs

| Job | 职责 |
|-----|------|
| `prepare-frontend` | `bun run build:tauri` 一次，artifact 供 mac/win/linux 复用 |
| `build-macos-arm` | 主路径发 Release |
| `build-macos-x64` | macOS Intel (x86_64) 追加 dmg/tar.gz/.sig |
| `build-windows` | Windows 追加资产（finalize 门禁平台） |
| `build-linux` | Linux 追加资产（不阻塞 finalize） |
| `finalize-release` | Mac+Win 完成后：`latest.json` + sha256 + verify |
| `deploy-website` | secrets 已配时：brand `website-v*` tag + CF hook（不阻塞 OTA） |
| `refinalize-after-linux` | Linux 上传后重跑 finalize + verify |
| `redeploy-website-after-linux` | secrets 已配时：Linux 资产上线后 redeploy |

`trigger-website-release.sh`：`deploy-website` job 内 `REQUIRE_WEBSITE_DEPLOY=true`。agent 仓未配 `BRAND_RELEASE_PAT`/`CF_PAGES_DEPLOY_HOOK` 时跳过该 job；改在 brand 仓打 `website-v*` tag（`website-release.yml` 含 `CF_PAGES_DEPLOY_HOOK`）。

`collect-bundle-assets.sh`：`find` 收集 bundle 资产；Bash 3.2 兼容（macOS GHA 无 `mapfile`）；workflow upload 步亦用 `while read`。

## Secrets（myrm-agent 仓库）

| Secret | 用途 |
|--------|------|
| `BRAND_RELEASE_PAT` | 对 `Pursue-LLL/myrm-agent-brand` contents:write；未配置时 `deploy-website` skip |
| `CF_PAGES_DEPLOY_HOOK` | Cloudflare Pages hook；未配置时 `deploy-website` skip（改在 brand 仓打 `website-v*`） |
| `TAURI_SIGNING_PRIVATE_KEY` | Tauri updater 包签名；与 `tauri.conf.json#plugins.updater.pubkey` 成对 |

## OTA manifest 匹配规则

`latest.json` 仅纳入 **updater 包**（`.app.tar.gz` / `.nsis.zip` / `.AppImage.tar.gz` 等）且存在配对 `.sig` 的平台。安装包 `.exe.sig` / `.msi.sig` 不计入 OTA。Linux job 设 `NO_STRIP=true` + `libfuse2` 以稳定 AppImage 打包。
| `APPLE_*` / `KEYCHAIN_PASSWORD` | 可选；未配置时 Mac job 不传 env，避免空证书触发 codesign 失败；OTA 仍靠 minisign |

## 依赖

- 父模块 [../_ARCH.md](../_ARCH.md)
- 营销站发布契约：`myrm-agent-brand/myrm-website/scripts/release-website.ts` (POS: tag + Deploy Hook 手动发布入口)
