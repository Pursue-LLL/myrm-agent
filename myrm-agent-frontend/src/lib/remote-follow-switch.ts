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
 * 重启后端并重挂健康监控。Rust 端成功后广播 `app:connections-changed` 事件，
 * 由全局监听统一驱动所有窗口 reload（含 session windows）；老构建无此命令时
 * 回退手动 reload，保证 UI 状态一致。
 */

import { isTauriRuntime } from './deploy-mode';

export async function switchRemoteFollow(deferred: boolean): Promise<void> {
  if (!isTauriRuntime()) {
    return;
  }
  try {
    const { invoke } = await import('@tauri-apps/api/core');
    // 成功路径由 Rust 端 emit 的 `app:connections-changed` 驱动全局 reload
    await invoke('switch_remote_follow', { deferred });
  } catch {
    // 老构建无此命令：回退手动刷新，保证 UI 状态一致
    window.location.reload();
  }
}
