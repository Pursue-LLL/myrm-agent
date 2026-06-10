# desktop-release CI 脚本

## 架构概述

桌面 GitHub Release 流水线辅助脚本；由 `.github/workflows/desktop-release.yml` 按 job 调用。

## 文件清单

| 文件 | 职责 |
|------|------|
| `inject-version.sh` | tag → `myrm-agent-desktop/src-tauri/tauri.conf.json` 版本 |
| `sync-server-venv.sh` | 生产 sidecar venv（`--no-group dev`） |
| `download-cloudflared-for-target.sh` | 按 target triple 下载单个 cloudflared 二进制 |
| `finalize-release.sh` | 下载 Release 资产 → 匹配 updater 包 + `.sig` → 生成 `latest.json`（无平台匹配则 fail）+ `.sha256` → upload |
| `check-updater-pubkey.sh` | 构建前校验 pubkey 与 `TAURI_SIGNING_PRIVATE_KEY` 一致性；占位符仅 warning |
| `trigger-website-release.sh` | brand `main` 打 `website-v{semver}` tag + POST CF Pages Deploy Hook |

## Workflow jobs

| Job | 职责 |
|-----|------|
| `prepare-frontend` | `bun run build:tauri` 一次，artifact 供 mac/win/linux 复用 |
| `build-macos-arm` | 主路径发 Release |
| `build-extra-platforms` | Win/Linux 追加资产 |
| `finalize-release` | `latest.json` + sha256 + 官网 trigger |

`trigger-website-release.sh`：`REQUIRE_WEBSITE_DEPLOY=true`（CI 默认）时缺 Secret **exit 1**；本地 dry run 设 `REQUIRE_WEBSITE_DEPLOY=false`。

## Secrets（myrm-agent 仓库）

| Secret | 用途 |
|--------|------|
| `BRAND_RELEASE_PAT` | 对 `Pursue-LLL/myrm-agent-brand` contents:write；未配置且 `REQUIRE_WEBSITE_DEPLOY=true` 时 finalize **失败** |
| `CF_PAGES_DEPLOY_HOOK` | Cloudflare Pages `website-release` hook；未配置且 `REQUIRE_WEBSITE_DEPLOY=true` 时 finalize **失败** |
| `TAURI_SIGNING_PRIVATE_KEY` | Tauri updater 包签名；与 `tauri.conf.json#plugins.updater.pubkey` 成对 |

## 依赖

- 父模块 [../_ARCH.md](../_ARCH.md)
- 营销站发布契约：`myrm-agent-brand/myrm-website/scripts/release-website.ts` (POS: tag + Deploy Hook 手动发布入口)
