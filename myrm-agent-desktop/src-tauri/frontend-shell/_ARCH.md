# frontend-shell 模块架构

## 架构概述

Release 模式 WebView 占位页：`tauri.conf.json#build.frontendDist` 指向本目录。Dev 模式直连 `devUrl`（`:3000`），不加载此页。

父模块：[../../_ARCH.md](../../_ARCH.md)

## 文件清单

| 文件 | 职责 |
|------|------|
| `index.html` | `withGlobalTauri` IPC 读取 `webui_port` → 轮询 Next standalone；`frontend-start-failed` 阻断跳转；`backend-start-failed` 警告后继续 |

## 约束

- 静态单文件，无构建步骤；Launch Contract 由 `scripts/ci/verify-launch-contract.sh` 静态校验
- Next standalone 资源由 `tauri.conf.json#bundle.resources` 打入 `frontend/`
