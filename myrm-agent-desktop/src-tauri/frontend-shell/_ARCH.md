# frontend-shell 模块架构

[INPUT]
- Tauri IPC frontend-start-failed、backend-start-failed 事件
- URL 查询参数 `startup_error`（Rust 在极早失败时带回的启动原因）

[OUTPUT]
- Release 启动面板：只显示启动/失败状态；Rust 在 Next standalone 就绪后导航，后端启动失败时携带 `startup_error` 回到本页显示原因

[POS]
tauri.conf.json#build.frontendDist 静态单文件；Dev 模式不加载。

## 架构概述

Release 模式启动面板：`tauri.conf.json#build.frontendDist` 指向本目录。本页**不做端口轮询、也不自行跳转**：
Rust 在 Next standalone 就绪后导航到产品页；若后端启动失败，Rust 会带 `startup_error` 查询参数导航回本页，
由本页直接显示失败原因（事件监听可能因极早失败而错过，查询参数是兜底）。Dev 模式直连 `devUrl`（`:3000`），不加载此页。

父模块：[../../_ARCH.md](../../_ARCH.md)

## 文件清单

| 文件 | 职责 |
|------|------|
| `index.html` | 产品级同构骨架屏（Progressive Skeleton Shell）：IPC 读取系统配置；0.05s 瞬时呈现工作台轮廓；监听启动失败事件并读取 `startup_error` 查询参数提供自愈指引；导航由 Rust 统一驱动；系统设置了「减少动态效果」时所有循环动画静止 |

## 约束

- 静态单文件，无构建步骤；Launch Contract 由 `scripts/ci/verify-launch-contract.sh` 静态校验
- Next standalone 资源由 `tauri.conf.json#bundle.resources` 打入 `frontend/`
- 只服务主窗口首屏：跳转目标固定为产品根路径，路径与查询不会保留。会话窗与宠物浮层不经此页，直接以 `runtime/product_origin.rs` 构造的完整地址开窗
