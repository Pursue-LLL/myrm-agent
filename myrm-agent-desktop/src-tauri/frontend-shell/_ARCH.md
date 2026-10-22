# frontend-shell 模块架构

[INPUT]
- Tauri IPC frontend-start-failed、backend-start-failed 事件

[OUTPUT]
- Release 启动面板：只显示启动/失败状态；导航由 Rust 在自己拉起的 Next 就绪后统一触发

[POS]
tauri.conf.json#build.frontendDist 静态单文件；Dev 模式不加载。

## 架构概述

Release 模式启动面板：`tauri.conf.json#build.frontendDist` 指向本目录。本页**不做端口轮询、也不自行跳转**：
由 Rust 在确认自己拉起的 Next standalone 就绪后统一 `navigate`，避免页面抢先跳到占用同一端口的其它服务，
渲染出残缺界面。Dev 模式直连 `devUrl`（`:3000`），不加载此页。

父模块：[../../_ARCH.md](../../_ARCH.md)

## 文件清单

| 文件 | 职责 |
|------|------|
| `index.html` | `withGlobalTauri` IPC 读取 `webui_port` → 轮询 Next standalone；`frontend-start-failed` 阻断跳转；`backend-start-failed` 警告后继续 |

## 约束

- 静态单文件，无构建步骤；Launch Contract 由 `scripts/ci/verify-launch-contract.sh` 静态校验
- Next standalone 资源由 `tauri.conf.json#bundle.resources` 打入 `frontend/`
- 只服务主窗口首屏：跳转目标固定为产品根路径，路径与查询不会保留。会话窗与宠物浮层不经此页，直接以 `runtime/product_origin.rs` 构造的完整地址开窗
