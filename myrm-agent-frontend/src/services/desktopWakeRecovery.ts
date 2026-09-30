/**
 * [INPUT]
 * @/store/useChatStore::useChatStore (POS: 活跃聊天与会话状态管理)
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

export interface WakeEventPayload {
  phase: 'waking' | 'ready';
  timestamp: number;
  sidecar_alive?: boolean | null;
  reason?: string;
}

export type UnlistenFn = () => void;

/**
 * 核心两阶段状态流转与会话自愈处理器
 */
export async function handleWakePhaseTransition(
  payload: WakeEventPayload,
  dependencies = {
    getState: useChatStore.getState,
  },
): Promise<void> {
  const store = dependencies.getState();

  if (payload.phase === 'waking') {
    store.setWakeRecovering(true);
    return;
  }

  if (payload.phase === 'ready') {
    store.setWakeRecovering(false);

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
  }
}

/**
 * 注册桌面端系统唤醒监听器
 * 支持 Tauri 原生事件通道，并自动回退到浏览器 visibilitychange/online
 */
export async function setupDesktopWakeRecovery(): Promise<UnlistenFn> {
  let tauriUnlisten: UnlistenFn | null = null;

  // 1. 尝试注册 Tauri 原生事件通道
  if (typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window) {
    try {
      const { listen } = await import('@tauri-apps/api/event');
      tauriUnlisten = await listen<WakeEventPayload>('app:system-wake', (event) => {
        void handleWakePhaseTransition(event.payload);
      });
      console.log('[WakeRecovery] Subscribed to native app:system-wake event');
    } catch (err) {
      console.warn('[WakeRecovery] Tauri event listener registration failed, falling back to Web API:', err);
    }
  }

  // 2. Web API 兜底（visibilitychange & online 事件）
  let webCleanup: (() => void) | null = null;
  if (typeof window !== 'undefined' && typeof document !== 'undefined') {
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        void handleWakePhaseTransition({
          phase: 'ready',
          timestamp: Date.now(),
          sidecar_alive: true,
          reason: 'web_visibility_visible',
        });
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

    webCleanup = () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange);
      window.removeEventListener('online', handleOnline);
    };
  }

  return () => {
    if (tauriUnlisten) {
      tauriUnlisten();
    }
    if (webCleanup) {
      webCleanup();
    }
  };
}
