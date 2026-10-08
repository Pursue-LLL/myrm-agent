import { AppRouterInstance } from 'next/dist/shared/lib/app-router-context.shared-runtime';
import { parseIntentUrl, redactIntentUrl, UIPIntent } from './schema';
import { consumeDesktopOAuth } from '@/lib/desktop-oauth';
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
  cloudProfileName: string;
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
   * Desktop OAuth 回调：校验本机发起的授权（state 匹配且未过期，一次性），用控制平面的一次性
   * exchange 换出会话 token，沙箱列表校验通过后才落为 Cloud 档案。
   * 任何校验失败都零副作用，不动本地会话。
   */
  private async handleOAuthCallback(exchange: string, state: string) {
    const LOCAL_TOKEN_BACKUP_KEY = 'myrm-local-auth-token-backup';
    try {
      const cpBaseUrl = consumeDesktopOAuth(state);
      if (!cpBaseUrl) {
        throw new Error('No matching pending OAuth request');
      }

      const redeemRes = await fetch(`${cpBaseUrl}/api/auth/oauth/exchange`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ exchange }),
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

      // 先验后写：token 有效性用沙箱列表校验，通过后才动本地会话，失败零副作用。
      const res = await fetch(`${cpBaseUrl}/api/sandboxes`, {
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        cache: 'no-store',
      });
      if (!res.ok) {
        throw new Error(`Sandbox discovery failed: ${res.status}`);
      }

      const current = window.localStorage.getItem('auth_token');
      if (current && current !== token && !window.localStorage.getItem(LOCAL_TOKEN_BACKUP_KEY)) {
        window.localStorage.setItem(LOCAL_TOKEN_BACKUP_KEY, current);
      }

      const { default: useAuthStore } = await import('@/store/useAuthStore');
      await useAuthStore.getState().login(token, { id: userId, email });

      const { addRemoteProfile, listRemoteProfiles, setActiveRemoteProfileId } =
        await import('@/lib/remote-profiles');
      const proxyBase = `${cpBaseUrl}/proxy/me`;
      const existing = listRemoteProfiles().find((p) => p.url === proxyBase);
      if (existing) {
        setActiveRemoteProfileId(existing.id);
      } else {
        addRemoteProfile(this.messages.cloudProfileName, proxyBase, { kind: 'cloud', cpBaseUrl });
      }

      toast.success(this.messages.oauthSuccess);
      this.router.push('/settings');
    } catch {
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
