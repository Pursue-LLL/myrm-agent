# config/adapters/

`ConfigSyncManager` 平台适配器：本地 Tauri vs Sandbox 配置读写与离线队列。

| 文件                | 职责                                                                                                                                                                                      |
| ------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `BaseAdapter.ts`    | 适配器抽象与共享逻辑：deviceId、版本号；两个适配器共用的失败答复 `BACKEND_NOT_AVAILABLE_ERROR` / `backendUnavailableSyncResult()` 与 `isTransportFailure()`（`fetch()` 没拿到应答的判定） |
| `TauriAdapter.ts`   | 桌面端本地配置 + Next 代理 5xx 处理；请求失败调 `markLocalBackendUnreachable`                                                                                                             |
| `SandboxAdapter.ts` | 云沙箱 CP 配置 API                                                                                                                                                                        |
| `index.ts`          | 适配器注册与工厂（白名单 barrel）                                                                                                                                                         |

## 失败接口约定

两个适配器对「后端够不着」给出同一种答复，同步层据此决定写入是保留重试还是丢弃：

- 读取（`getAll` / `get`）：只有后端明确答复才返回值，404 是「没有这一行」。后端不可用、请求失败或超时、会话过期（Sandbox 的 401）一律抛错，调用方（`ensureKeyLoaded`）才能把「不知道」和「没有」分开。Sandbox 的 `getAll` 遇 401 仍返回空表，按需读取单个 key 时由 `get` 的 401 抛错补上这个区分。
- 写入（`sync`）：没送达就返回 `backendUnavailableSyncResult()`（`error: 'Backend not available'`），不抛错。Tauri：请求失败、超时、数据库未就绪、Next 代理 500 / 502 / 503 / 504；Sandbox：请求失败、超时、401 / 408 / 429 / 502 / 503 / 504。其余非 2xx 抛 `ConfigSyncError`：云端 500 是服务端的应用错误，原样重发不会成功，不按「不可用」重试。
- 请求失败只在 `fetch()` 调用处判定：各浏览器措辞不同（Failed to fetch / Load failed / NetworkError ...）但都是 `TypeError`，另有适配器自己的超时 `AbortError`；处理应答时的 `TypeError` 是缺陷，照常抛出，不被当成网络问题吞掉。
