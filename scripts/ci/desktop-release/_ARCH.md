# desktop-release CI 脚本

## 架构概述

桌面 GitHub Release 流水线辅助脚本；由 `.github/workflows/desktop-release.yml` 按 job 调用。

## 文件清单

| 文件 | 职责 |
|------|------|
| `inject-version.sh` | tag → `myrm-agent-desktop/src-tauri/tauri.conf.json` 版本 |
| `sync-server-venv.sh` | 生产 sidecar venv（`--no-group dev`） |
| `download-cloudflared-for-target.sh` | 按 target triple 下载单个 cloudflared 二进制 |
| `finalize-release.sh` | 下载 Release 资产 → 生成 `latest.json` + 逐文件 `.sha256` → upload |
| `trigger-website-release.sh` | brand `main` 打 `website-v{semver}` tag + POST CF Pages Deploy Hook |

## Secrets（myrm-agent 仓库）

| Secret | 用途 |
|--------|------|
| `BRAND_RELEASE_PAT` | 对 `Pursue-LLL/myrm-agent-brand` contents:write；未配置则跳过官网触发 |
| `CF_PAGES_DEPLOY_HOOK` | Cloudflare Pages `website-release` hook；未配置则跳过 |

## 依赖

- 父模块 [../_ARCH.md](../_ARCH.md)
- 营销站发布契约：`myrm-agent-brand/myrm-website/scripts/release-website.ts` (POS: tag + Deploy Hook 手动发布入口)
