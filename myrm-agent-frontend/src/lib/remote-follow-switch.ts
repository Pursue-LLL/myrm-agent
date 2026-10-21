/**
 * [INPUT]
 * - @/lib/deploy-mode::isTauriRuntime (POS: Tauri 运行时判定)
 * - @tauri-apps/api/core::invoke (POS: Rust command 通道，动态 import)
 *
 * [OUTPUT]
 * - switchRemoteFollow: remote_follow 切换唯一前端入口。
 *
 * [POS]
 * 连接档案切换的后端生命周期编排入口。切 remote（deferred=true）优雅停本地后端
 * （watchdog/wake 先停、服务端 drain 自退、兜底强杀）；切回本地（deferred=false）
 * 重启后端并重挂健康监控。成功后 Rust 端广播 `app:connections-changed`，由全局
 * 监听统一驱动所有窗口 reload（含 session windows）；编排失败一律向调用方抛错
 * （调用方 toast 提示并保持 UI 状态不变，可安全重试）。
 */

import { isTauriRuntime } from './deploy-mode';

export async function switchRemoteFollow(deferred: boolean): Promise<void> {
  if (!isTauriRuntime()) {
    return;
  }
  const { invoke } = await import('@tauri-apps/api/core');
  await invoke('switch_remote_follow', { deferred });
}
