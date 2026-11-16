/**
 * [INPUT]
 * - @/store/useChatStore::useChatStore (POS: Active chat state manager.)
 * - @/lib/deploy-mode::resolveInjectedE2eApiBase (POS: 前端部署模式与基础地址解析层。)
 *
 * [OUTPUT]
 * - isLocalDevHost / resolveE2eApiBase / resolveChatIdFromLocation: page-environment probes (local dev host, injected E2E backend origin, chat id already in the route)
 * - prepareAutomationSend: switch fast mode to agent before an automated send
 * - requireE2eChatBridge: the mounted `window.__MYRM_E2E_CHAT__`, or a thrown error
 *
 * [POS]
 * 开发桥的页面环境探针：本机开发主机判定、注入的 E2E 后端基址、路由里已有的聊天 id、自动化发送前的模式矫正，以及已挂载桥的读取。
 */
import useChatStore from '@/store/useChatStore';
import { resolveE2eApiBase as resolveInjectedE2eApiBase } from '@/lib/deploy-mode';

export function isLocalDevHost(): boolean {
  if (typeof window === 'undefined') {
    return false;
  }
  const host = window.location.hostname;
  return host === '127.0.0.1' || host === 'localhost';
}

export function prepareAutomationSend(): void {
  const { actionMode, setActionMode } = useChatStore.getState();
  if (actionMode === 'fast') {
    setActionMode('agent');
  }
}

export function resolveE2eApiBase(): string {
  return resolveInjectedE2eApiBase() ?? '';
}

/**
 * A chat id already present in the route (``/<chatId>``), so a bridge-bound page keeps the chat it opened.
 * Only ids the app actually mints are adopted (a server UUID, or the local ``c-…`` form): a dev bridge mounted
 * on a non-chat page (``/settings``) must still open a fresh chat, as it did before.
 */
export function resolveChatIdFromLocation(): string | undefined {
  if (typeof window === 'undefined') {
    return undefined;
  }
  const segments = window.location.pathname.split('/').filter(Boolean);
  if (segments.length !== 1) {
    return undefined;
  }
  const [segment] = segments;
  const isChatId =
    segment.startsWith('c-') || /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(segment);
  return isChatId ? segment : undefined;
}

export function requireE2eChatBridge(): NonNullable<Window['__MYRM_E2E_CHAT__']> {
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge) {
    throw new Error('E2E chat bridge not initialized');
  }
  return bridge;
}
