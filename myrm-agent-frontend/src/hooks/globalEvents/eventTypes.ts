/**
 * [INPUT]
 * - @/lib/utils/toast::toast (POS: 应用统一 toast 入口，仅取类型)
 *
 * [OUTPUT]
 * - SSEPayload: 服务端推送事件的外壳
 * - GlobalEventDeps / GlobalEventHandler: 事件处理器所需的翻译、路由、toast、跨标签页通知与防抖计时器
 * - PushToast / GlobalEventTranslator / DebounceTimers: 上述依赖的具体类型
 *
 * [POS]
 * 全局事件处理器的共享契约。处理器是 (payload, deps) 的函数，不依赖 React，便于单测。
 */
import type { AppRouterInstance } from 'next/dist/shared/lib/app-router-context.shared-runtime';

import type { toast } from '@/lib/utils/toast';

export interface SSEPayload {
  type: string;
  data: Record<string, unknown>;
  timestamp: string;
}

export type GlobalEventTranslator = (key: string, values?: Record<string, string | number>) => string;

type ToastLevel = 'info' | 'success' | 'warning' | 'error';

/** The app toast, silenced as a whole while web notifications are switched off. */
export type PushToast = { [K in ToastLevel]: (...args: Parameters<(typeof toast)[K]>) => void } & {
  dismiss: (typeof toast)['dismiss'];
};

/** Pending debounced refetch timers by key; the owner clears them when it unmounts. */
export interface DebounceTimers {
  current: Record<string, ReturnType<typeof setTimeout>>;
}

export interface GlobalEventDeps {
  router: Pick<AppRouterInstance, 'push'>;
  /** Translator of the `notifications` namespace. */
  t: GlobalEventTranslator;
  /** Translator of the `backgroundTasks.idleStatus` namespace. */
  tIdle: GlobalEventTranslator;
  /** Translator of the `kanban` namespace. */
  tKanban: GlobalEventTranslator;
  pushToast: PushToast;
  /** System notification, raised only by the tab that owns the stream and only while notifications are on. */
  notifyIfLeader: (title: string, body?: string, onClick?: () => void) => void;
  debouncedRefetches: DebounceTimers;
}

export type GlobalEventHandler = (payload: SSEPayload, deps: GlobalEventDeps) => void;
