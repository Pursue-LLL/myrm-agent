import { AppRouterInstance } from 'next/dist/shared/lib/app-router-context.shared-runtime';
import { parseIntentUrl, UIPIntent } from './schema';
import { toast } from 'sonner';

/**
 * [POS] Universal Intent Protocol (UIP) Dispatcher.
 * Executes the validated intent by interacting with the Next.js router or global state.
 * Supports both raw URL parsing and page-provided parsed intents.
 */

export class IntentDispatcher {
  private router: AppRouterInstance;
  private openFlowPad: (text: string) => void;

  constructor(router: AppRouterInstance, openFlowPad: (text: string) => void) {
    this.router = router;
    this.openFlowPad = openFlowPad;
  }

  public async dispatch(rawUrl: string, parsedIntent?: UIPIntent): Promise<boolean> {
    try {
      console.log(`[UIP] Received deep link: ${rawUrl}`);
      const intent = parsedIntent ?? parseIntentUrl(rawUrl);
      await this.execute(intent);
      return true;
    } catch (error) {
      console.error('[UIP] Dispatch failed:', error);
      toast.error('无效的外部链接或参数错误');
      return false;
    }
  }

  /**
   * Desktop OAuth 回调：持久化 CP token 并用沙箱列表校验，成功后落为 Cloud 档案。
   * 用户在浏览器点“回到桌面”显式触发，无静默登录；校验失败则清 token 防错绑。
   */
  private async handleOAuthCallback(token: string) {
    const LOCAL_TOKEN_BACKUP_KEY = 'myrm-local-auth-token-backup';
    const { CLOUD_OAUTH_PENDING_KEY } = await import('@/lib/remote-profiles');
    try {
      const pendingRaw =
        typeof window !== 'undefined' ? window.localStorage.getItem(CLOUD_OAUTH_PENDING_KEY) : null;
      const pending = pendingRaw ? (JSON.parse(pendingRaw) as { cpBaseUrl?: string }) : null;
      const cpBaseUrl =
        typeof pending?.cpBaseUrl === 'string' ? pending.cpBaseUrl.replace(/\/+$/, '') : null;

      // 先验后写：token 有效性用沙箱列表校验，通过后才动本地会话，失败零副作用。
      if (cpBaseUrl) {
        const res = await fetch(`${cpBaseUrl}/api/sandboxes`, {
          headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
          cache: 'no-store',
        });
        if (!res.ok) {
          throw new Error(`Sandbox discovery failed: ${res.status}`);
        }
      }

      if (typeof window !== 'undefined') {
        const current = window.localStorage.getItem('auth_token');
        if (current && current !== token && !window.localStorage.getItem(LOCAL_TOKEN_BACKUP_KEY)) {
          window.localStorage.setItem(LOCAL_TOKEN_BACKUP_KEY, current);
        }
        window.localStorage.removeItem(CLOUD_OAUTH_PENDING_KEY);
      }

      const { default: useAuthStore } = await import('@/store/useAuthStore');
      await useAuthStore.getState().login(token);

      if (cpBaseUrl) {
        const { addRemoteProfile, listRemoteProfiles, setActiveRemoteProfileId } = await import(
          '@/lib/remote-profiles'
        );
        const proxyBase = `${cpBaseUrl}/proxy/me`;
        const existing = listRemoteProfiles().find((p) => p.url === proxyBase);
        if (existing) {
          setActiveRemoteProfileId(existing.id);
        } else {
          addRemoteProfile('Cloud sandbox', proxyBase, { kind: 'cloud', cpBaseUrl });
        }
      }

      toast.success('授权成功');
      this.router.push('/settings');
    } catch {
      toast.error('授权校验失败，请重试');
      this.router.push('/settings');
    }
  }

  private async execute(intent: UIPIntent) {
    console.log(`[UIP] Executing intent:`, intent);

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
        await this.handleOAuthCallback(intent.token);
        break;
      case 'install-skill':
        this.router.push(`/settings/skills?action=install&url=${encodeURIComponent(intent.url)}`);
        break;
    }
  }
}
