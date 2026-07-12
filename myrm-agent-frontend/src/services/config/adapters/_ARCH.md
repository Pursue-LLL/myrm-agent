# config/adapters/

`ConfigSyncManager` 平台适配器：本地 Tauri vs Sandbox 配置读写与离线队列。

| 文件 | 职责 |
|------|------|
| `BaseAdapter.ts` | 适配器抽象与共享逻辑 |
| `TauriAdapter.ts` | 桌面端本地配置 + Next 代理 5xx 处理 |
| `SandboxAdapter.ts` | 云沙箱 CP 配置 API |
| `index.ts` | 适配器注册与工厂（白名单 barrel） |
