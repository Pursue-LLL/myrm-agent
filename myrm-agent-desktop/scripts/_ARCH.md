# myrm-agent-desktop/scripts 模块架构

## 架构概述

桌面仓本地构建与发版验签辅助脚本。由 `myrm-agent-desktop/_ARCH.md` 引用；CI 桌面流水线见 [../../scripts/ci/desktop-release/_ARCH.md](../../scripts/ci/desktop-release/_ARCH.md)。

## 文件清单

| 文件 | 平台 | 职责 | I/O/P |
|------|------|------|-------|
| `check-fractal-docs.ts` | CI | 分形文档门禁：必检 `_ARCH.md` 清单 + 核心 `[INPUT]` 头；`bun run scripts/check-fractal-docs.ts` | ✅ |
| `check-fractal-docs.test.ts` | CI | 门禁单元测试 | — |
| `build-frontend.sh` | Unix | 从 desktop 根解析 monorepo 路径，在 `myrm-agent-frontend/` 执行 `build:tauri`（或 `dev` 模式 `bun run dev`）；standalone 已存在则跳过构建 | ✅ |
| `verify-signing.sh` | Unix (macOS CI) | 发版后 codesign / Gatekeeper / notary staple 四重验签；失败计数作为 exit code | ✅ |
| `verify-signing.ps1` | Windows | Windows 安装包签名验证（与 `verify-signing.sh` 对称） | ✅ |
| `inset-app-icon.py` | 双平台 | 从 `myrm-agent-frontend/public/brand` 源图生成 PWA/Tauri/tray 图标（`cargo tauri icon`）；维护者手动运行 | ✅ |

## 约束

- Python 仅 `inset-app-icon.py`（品牌图标生成）；后端或 sidecar 打包见 `sidecar/build.py`
- 发版编排脚本在仓库根 `scripts/ci/desktop-release/`，不在本目录
