# shared/ 模块架构

## 架构概述

`myrm-agent` 仓内前后端共享的静态契约（authoring SSOT，非 harness 记忆数据）。

**Disambiguation**

- 不是 `app/services/memory/shared_context`（共享记忆上下文）
- 不是前端 `components/security/shared`（UI 组件目录）

## 打包契约

| 部署面 | 消费方式 |
|--------|----------|
| 本地 monorepo dev | Server [providers.py](../myrm-agent-server/app/services/agent/params/providers.py) 读 `myrm-agent/shared/config/`；Frontend `@shared/config/*` |
| Docker server 镜像 | `COPY shared /shared` → server 读 `/shared/config/` |
| Tauri PyInstaller sidecar | `sidecar/build.py` `--add-data` → `_MEIPASS/shared/config/` |
| Frontend Docker build | builder 阶段 COPY `shared/` 到 `/app/shared`（配合 `next.config.ts` monorepoRoot） |

## 子目录

| 目录 | 职责 | 文档 |
|------|------|------|
| `config/` | 跨端 JSON 配置 | [_ARCH.md](config/_ARCH.md) |
