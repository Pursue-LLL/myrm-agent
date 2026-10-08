import { AppRouterInstance } from 'next/dist/shared/lib/app-router-context.shared-runtime';
import { parseIntentUrl, redactIntentUrl, UIPIntent } from './schema';
import { consumeDesktopOAuth, peekDesktopOAuth } from '@/lib/desktop-oauth';
import { toast } from 'sonner';

/**
 * [POS] Universal Intent Protocol (UIP) Dispatcher.
 * Executes the validated intent by interacting with the Next.js router or global state.
 * Supports both raw URL parsing and page-provided parsed intents.
 */

/** 用户可见的 toast 文案，由调用方按当前语言注入（dispatcher 本身不依赖 React i18n）。 */
export interface IntentMessages {
  invalidLink: string;
  oauthSuccess: string;
  oauthFailed: string;
  oauthBusy: string;
  cloudProfileName: string;
}

/** 查询失败按"无进行中会话"处理，与设置页连接切换的会话守卫一致。 */
async function hasActiveSessions(): Promise<boolean> {
  try {
    const { getActiveSessions } = await import('@/services/agent');
    const { activeSessions } = await getActiveSessions();
    return activeSessions.length > 0;
  } catch {
    return false;
  }
}

export class IntentDispatcher {
  private router: AppRouterInstance;
  private openFlowPad: (text: string) => void;
  private messages: IntentMessages;

  constructor(router: AppRouterInstance, openFlowPad: (text: string) => void, messages: IntentMessages) {
    this.router = router;
    this.openFlowPad = openFlowPad;
    this.messages = messages;
  }

  public async dispatch(rawUrl: string, parsedIntent?: UIPIntent): Promise<boolean> {
    try {
      console.log(`[UIP] Received deep link: ${redactIntentUrl(rawUrl)}`);
      const intent = parsedIntent ?? parseIntentUrl(rawUrl);
      await this.execute(intent);
      return true;
    } catch (error) {
      console.error('[UIP] Dispatch failed:', error);
      toast.error(this.messages.invalidLink);
      return false;
    }
  }

  /**
   * Desktop OAuth 回调：把一次深链登录落成真正的"切到云端"。顺序即不变式：
   * 1) 校验待决授权（state、TTL）但先不消耗，并确认没有进行中的本地会话（否则拒绝，待决授权保留，用户收尾后可重试）；
   * 2) 消耗授权、用 PKCE verifier 兑换 token、沙箱列表校验 token——这一步及之前任何失败都零副作用；
   * 3) 先切换连接（停本地 sidecar、广播连接变更，窗口随后重载），成功后才改本地会话与档案。
   */
  private async handleOAuthCallback(exchange: string, state: string) {
    try {
      if (!peekDesktopOAuth(state)) {
        throw new Error('No matching pending OAuth request');
      }
      if (await hasActiveSessions()) {
        toast.error(this.messages.oauthBusy);
        return;
      }
      const session = consumeDesktopOAuth(state);
      if (!session) {
        throw new Error('Pending OAuth request expired');
      }
      const { cpBaseUrl, codeVerifier } = session;

      const redeemRes = await fetch(`${cpBaseUrl}/api/auth/oauth/exchange`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ exchange, code_verifier: codeVerifier }),
        cache: 'no-store',
      });
      if (!redeemRes.ok) {
        throw new Error(`Exchange redemption failed: ${redeemRes.status}`);
      }
      const redeemed = (await redeemRes.json()) as { token?: string; user_id?: string; email?: string };
      const { token, user_id: userId, email = '' } = redeemed;
      if (!token || !userId) {
        throw new Error('Exchange response is incomplete');
      }

      const res = await fetch(`${cpBaseUrl}/api/sandboxes`, {
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        cache: 'no-store',
      });
      if (!res.ok) {
        throw new Error(`Sandbox discovery failed: ${res.status}`);
      }

      // 先载入后续依赖：切换会在约 250ms 后触发窗口重载，切换之后只剩同步操作。
      const [{ default: useAuthStore }, { ensureCloudProfile }, { switchRemoteFollow }, { backupLocalAuthToken }] =
        await Promise.all([
          import('@/store/useAuthStore'),
          import('@/lib/remote-profiles'),
          import('@/lib/remote-follow-switch'),
          import('@/lib/deploy-mode'),
        ]);
      await switchRemoteFollow(true);

      backupLocalAuthToken();
      await useAuthStore.getState().login(token, { id: userId, email });
      if (!ensureCloudProfile(this.messages.cloudProfileName, cpBaseUrl)) {
        throw new Error('Cloud profile could not be created');
      }

      toast.success(this.messages.oauthSuccess);
      this.router.push('/settings/system');
    } catch (error) {
      console.warn('[UIP] OAuth callback rejected:', error instanceof Error ? error.message : 'unknown error');
      toast.error(this.messages.oauthFailed);
      this.router.push('/settings');
    }
  }

  private async execute(intent: UIPIntent) {
    console.log(`[UIP] Executing intent: ${intent.action}`);

    // Ensure the window is visible and focused when receiving a deep link
    if (typeof window !== 'undefined' && window.__TAURI_INTERNALS__) {
      try {
        // Dynamic import keeps browser/desktop APIs out of SSR evaluation.
        const { getCurrentWindow } = await import('@tauri-apps/api/window');
        const appWindow = getCurrentWindow();
        // Ensure tray-hidden windows can be restored before focusing.
        await appWindow.show();
        await appWindow.unminimize();
        await appWindow.setFocus();
      } catch (e) {
        console.error('[UIP] Failed to focus window:', e);
      }
    }

    switch (intent.action) {
      case 'chat':
        this.router.push(`/chat/${intent.id}`);
        break;
      case 'agent':
        this.router.push(`/agents/${intent.id}`);
        break;
      case 'ask':
        this.openFlowPad(intent.text);
        break;
      case 'oauth':
        await this.handleOAuthCallback(intent.exchange, intent.state);
        break;
      case 'install-skill':
        this.router.push(`/settings/skills?action=install&url=${encodeURIComponent(intent.url)}`);
        break;
    }
  }
}
