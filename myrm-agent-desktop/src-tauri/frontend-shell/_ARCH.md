# frontend-shell 模块架构

[INPUT]
- Tauri IPC frontend-start-failed、backend-start-failed 事件
- URL 查询参数 `startup_error`（Rust 在极早失败时带回的启动原因）
- 系统语言（`navigator.language`）：任一中文变体显示中文，其余显示英文

[OUTPUT]
- Release 启动面板：只显示启动/失败状态；Rust 在 Next standalone 就绪后导航，后端启动失败时携带 `startup_error` 回到本页显示原因

[POS]
tauri.conf.json#build.frontendDist 静态单文件；Dev 模式不加载。

## 架构概述

Release 模式启动面板：`tauri.conf.json#build.frontendDist` 指向本目录。本页**不做端口轮询、也不自行跳转**：
Rust 在 Next standalone 就绪后导航到产品页；若后端启动失败，Rust 会带 `startup_error` 查询参数导航回本页，
由本页直接显示失败原因（事件监听可能因极早失败而错过，查询参数是兜底）。Dev 模式直连 `devUrl`（`:3000`），不加载此页。

壳页与 Next 不同源，读不到 Next 来源下保存的界面语言与主题，所以语言取系统语言，配色固定为产品的默认深色。

失败面板分两层：本地化的处理指引（中/英）与 Rust 给出的原始原因（原样显示、可选中复制，供反馈问题时粘贴）。

父模块：[../../_ARCH.md](../../_ARCH.md)

## 文件清单

| 文件 | 职责 |
|------|------|
| `index.html` | 产品级同构骨架屏（Progressive Skeleton Shell）：0.05s 瞬时呈现工作台轮廓；全部可见文案以 JSON 内联在 `#shell-copy`（zh / en 两套，键必须一致且全部被使用，Launch Contract 校验）；监听启动失败事件并读取 `startup_error` 查询参数，显示本地化指引与原始原因；导航由 Rust 统一驱动；系统设置了「减少动态效果」时所有循环动画静止 |

## 约束

- 静态单文件，无构建步骤；Launch Contract 由 `scripts/ci/verify-launch-contract.sh` 静态校验
- 新增或修改文案必须同时给出 zh 与 en，写在 `#shell-copy` 里并用 `data-i18n` 或 `t("键")` 引用
- Next standalone 资源由 `tauri.conf.json#bundle.resources` 打入 `frontend/`
- 只服务主窗口首屏：跳转目标固定为产品根路径（`runtime/product_origin.rs` 的 `standalone_root`），路径与查询不会保留。会话窗与宠物浮层不经此页，直接以 `runtime/product_origin.rs` 构造的完整地址开窗
