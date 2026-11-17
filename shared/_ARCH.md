# shared/ 模块架构

## 架构概述

`myrm-agent` 仓内前后端共享的静态契约（authoring SSOT，非 harness 记忆数据）。

**Disambiguation**

- 不是 `app/services/memory/shared_context`（共享记忆上下文）
- 不是前端 `components/security/shared`（UI 组件目录）

## 打包契约

| 部署面 | 消费方式 |
|--------|----------|
| 本地 monorepo dev | Server [providers.py](../myrm-agent-server/app/services/agent/params/model_config/providers.py) 读 `myrm-agent/shared/config/`；Frontend `@shared/config/*` |
| Docker server 镜像 | `COPY shared /shared` → server 读 `/shared/config/` |
| Tauri PyInstaller sidecar | `sidecar/build.py` `--add-data` 只打入 `provider_legacy_remap.json` → `_MEIPASS/shared/config/` |
| Frontend Docker build | builder 阶段 COPY `shared/` 到 `/app/shared`（配合 `next.config.ts` monorepoRoot） |

服务端运行时读取的只有 `provider_legacy_remap.json`，所以桌面 sidecar 只打包这一个文件。其余 JSON（`kanban_move_guard.json`、`kanban_blocked_reasons.json`、`media_generation_contract.json`、`chat_input_limits.json`）服务端只在契约测试里读，运行时不读；Docker server 镜像按目录整体 `COPY shared /shared`，它们随目录在镜像里，但不会被读取。

## 子目录

| 目录 | 职责 | 文档 |
|------|------|------|
| `config/` | 跨端 JSON 配置 | [_ARCH.md](config/_ARCH.md) |
