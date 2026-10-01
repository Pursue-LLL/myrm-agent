/**
 * [INPUT]
 * @/store/useChatStore::useChatStore (POS: 活跃聊天与会话状态管理)
 * @/lib/deploy-mode::isTauriRuntime (POS: Tauri 运行时排他判定)
 * @/services/backgroundTasksRefresh::notifyBackgroundTasksChanged (POS: 后台任务即时刷新广播)
 * @tauri-apps/api/event::listen (POS: Tauri 原生事件接收通道)
 *
 * [OUTPUT]
 * setupDesktopWakeRecovery: 注册系统唤醒监听并协调活跃会话自愈。
 * handleWakePhaseTransition: 处理两阶段唤醒自愈纯逻辑（供单测使用）。
 *
 * [POS]
 * 桌面端系统唤醒自愈服务，消除开盖假死与半开死连接。
 */

import useChatStore from '@/store/useChatStore';
import { isTauriRuntime } from '@/lib/deploy-mode';
import { notifyBackgroundTasksChanged } from '@/services/backgroundTasksRefresh';

export interface WakeEventPayload {
  phase: 'waking' | 'ready';
  timestamp: number;
  sidecar_alive?: boolean | null;
  reason?: string;
}

export type UnlistenFn = () => void;

/** 浏览器端判定休眠挂起的最小后台时差阈值（10秒） */
const WEB_VISIBILITY_WAKE_THRESHOLD_MS = 10_000;

/**
 * 核心两阶段状态流转与会话自愈处理器
 */
export async function handleWakePhaseTransition(
  payload: WakeEventPayload,
  dependencies = {
    getState: useChatStore.getState,
    notifyBackgroundTasks: notifyBackgroundTasksChanged,
  },
): Promise<void> {
  if (payload.phase === 'waking') {
    // Phase 1：开盖即刻通知，静默感知准备
    return;
  }

  if (payload.phase === 'ready') {
    const store = dependencies.getState();
    const { chatId, loading, loadMessages, loadChatHistory, setLoading } = store;

    // 1. 若当前活跃会话处于流式 loading 状态，执行断点探活同步
    if (chatId && loading) {
      try {
        await loadMessages(chatId);
      } catch (err) {
        console.warn('[WakeRecovery] Failed to synchronize messages after wake:', err);
      } finally {
        // 解除假死转圈状态，让用户能够继续交互或查看已落盘消息
        setLoading(false);
      }
    }

    // 2. 静默刷新会话历史列表，让左侧磁贴解绑失效状态
    try {
      await loadChatHistory(1);
    } catch (err) {
      console.warn('[WakeRecovery] Failed to refresh chat history after wake:', err);
    }

    // 3. 协同刷新后台任务列表与系统托盘
    try {
      dependencies.notifyBackgroundTasks();
    } catch (err) {
      console.warn('[WakeRecovery] Failed to notify background tasks refresh:', err);
    }
  }
}

/**
 * 注册桌面端系统唤醒监听器
 * 在 Tauri 环境下严格仅监听原生 app:system-wake 事件；
 * 仅在纯 Web 浏览器环境下启用 Web API 兜底，杜绝切窗口误杀流式生成。
 */
export async function setupDesktopWakeRecovery(): Promise<UnlistenFn> {
  // 1. Tauri 桌面端：排他使用原生系统唤醒事件通道
  if (isTauriRuntime()) {
    try {
      const { listen } = await import('@tauri-apps/api/event');
      const tauriUnlisten = await listen<WakeEventPayload>('app:system-wake', (event) => {
        void handleWakePhaseTransition(event.payload);
      });
      console.log('[WakeRecovery] Subscribed to native app:system-wake event in Tauri runtime');
      return () => {
        tauriUnlisten();
      };
    } catch (err) {
      console.warn('[WakeRecovery] Failed to subscribe to Tauri app:system-wake event:', err);
      return () => undefined;
    }
  }

  // 2. 纯 Web 浏览器模式兜底（基于带时差阈值的 visibilitychange 与 online 事件）
  if (typeof window !== 'undefined' && typeof document !== 'undefined') {
    let lastHiddenTime = 0;

    const handleVisibilityChange = () => {
      if (document.visibilityState === 'hidden') {
        lastHiddenTime = Date.now();
      } else if (document.visibilityState === 'visible') {
        const now = Date.now();
        // 只有后台挂起超过阈值（10秒）才判定为休眠唤醒，防止短时间切标签页/切窗口误触发
        if (lastHiddenTime > 0 && now - lastHiddenTime >= WEB_VISIBILITY_WAKE_THRESHOLD_MS) {
          lastHiddenTime = 0;
          void handleWakePhaseTransition({
            phase: 'ready',
            timestamp: now,
            sidecar_alive: true,
            reason: 'web_visibility_visible',
          });
        }
      }
    };

    const handleOnline = () => {
      void handleWakePhaseTransition({
        phase: 'ready',
        timestamp: Date.now(),
        sidecar_alive: true,
        reason: 'web_online_event',
      });
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    window.addEventListener('online', handleOnline);

    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange);
      window.removeEventListener('online', handleOnline);
    };
  }

  return () => undefined;
}
